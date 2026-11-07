import logging
import time
from collections.abc import Callable
from typing import TypeVar, cast

from .attempt import Attempt
from .backoff import Backoff
from .config import WaitOptions, get_config
from .deadline import Deadline
from .exceptions import AttemptsExhaustedError, TimeoutExpiredError, WaitStoppedError, safe_repr, safe_str
from .types import UNSET, Clock
from .validators import validate_max_attempts

logger = logging.getLogger(__name__)

STOP_ON_TIMEOUT = "timeout"
STOP_ON_NO_TIME = "no_time_for_next_attempt"
STOP_ON_ATTEMPTS = "attempts"

SuccessCheck = Callable[[object], bool]

T = TypeVar("T")


def describe_predicate(predicate: object, message: str | None) -> str:
    """Построить человекочитаемое описание того, чего ждём.

    Адрес объекта и repr аргументов намеренно не используются: адрес бесполезен в отчёте,
    а repr может вынести в лог чувствительные данные.

    :param predicate: функция-предикат или другой вызываемый объект.
    :param message: описание, заданное пользователем; имеет приоритет.
    :return: описание для сообщения об ошибке.
    """
    if message is not None:
        return message
    name = cast("object", getattr(predicate, "__qualname__", None)) or cast(
        "object", getattr(predicate, "__name__", None)
    )
    if isinstance(name, str) and name:
        return name
    return type(predicate).__name__


class WaitLoop[T]:
    """Ядро ожидания без ввода-вывода.

    Хранит состояние ожидания и решает, что делать дальше, но ничего не выполняет само:
    вызов предиката и сон возложены на драйвер. За счёт этого синхронный и асинхронный
    варианты ожидания используют одну и ту же логику остановки, бэкоффа и диагностики.

    Причины остановки проверяются в фиксированном порядке: сначала наступивший дедлайн,
    затем исчерпание попыток, затем невозможность вместить следующую паузу до дедлайна.
    """

    def __init__(
        self,
        *,
        waiting_for: str,
        options: WaitOptions,
        succeeds_on: SuccessCheck = bool,
        clock: Clock = time.monotonic,
    ) -> None:
        """Инициализировать объект.

        :param waiting_for: значение настройки ``waiting_for``.
        :param options: параметры одного ожидания.
        :param succeeds_on: значение настройки ``succeeds_on``.
        :param clock: значение настройки ``clock``.
        """
        config = get_config()
        self._waiting_for = waiting_for
        timeout = config.timeout_seconds if options.timeout_seconds is None else options.timeout_seconds
        backoff = config.backoff if options.sleep_seconds is None else Backoff.parse(options.sleep_seconds)
        maximum = config.max_attempts if options.max_attempts is UNSET else options.max_attempts
        self._deadline = Deadline(timeout, clock=clock)
        self._delays = backoff.delays()
        self._max_attempts = validate_max_attempts(maximum)
        self._expected_exceptions = options.expected_exceptions
        self._retry_on_exception = options.retry_on_exception
        self._succeeds_on = succeeds_on
        self._attempts = 0
        self._is_satisfied = False
        self._last_result: T | None = None
        self._last_exception: Exception | None = None
        self._stop_reason = STOP_ON_TIMEOUT

    @property
    def waiting_for(self) -> str:
        """Получить описание того, чего ждём."""
        return self._waiting_for

    @property
    def attempts(self) -> int:
        """Получить число уже выполненных попыток."""
        return self._attempts

    @property
    def is_satisfied(self) -> bool:
        """Проверить, что условие ожидания выполнено."""
        return self._is_satisfied

    @property
    def stopped_on_attempts(self) -> bool:
        """Проверить, что ожидание прекращено из-за исчерпания попыток, а не по времени."""
        return self._stop_reason == STOP_ON_ATTEMPTS

    @property
    def value(self) -> T:
        """Получить результат, на котором ожидание завершилось успешно.

        Осмысленно только когда ``is_satisfied`` истинно и успехом считается truthy-результат.
        """
        # Успех по truthy-проверке исключает None, но выразить «truthy T» типами нельзя.
        return cast("T", self._last_result)

    def elapsed_seconds(self) -> float:
        """Получить время, прошедшее с начала ожидания, в секундах."""
        return self._deadline.elapsed_seconds()

    def expire_if_deadline_reached(self) -> bool:
        """Проверить дедлайн перед началом очередной попытки.

        Вызывается после сна, потому что проснуться можно позже заказанного: и ``time.sleep``,
        и event loop гарантируют только нижнюю границу паузы.

        :return: True, если начинать новую попытку уже нельзя.
        """
        if self._deadline.seconds_remaining() > 0:
            return False
        self._stop_reason = STOP_ON_TIMEOUT
        return True

    def start_attempt(self) -> None:
        """Отметить начало очередной попытки."""
        self._attempts += 1

    def is_expected(self, error: Exception) -> bool:
        """Проверить, что исключение предиката следует проигнорировать и повторить попытку.

        :param error: исключение, выброшенное предикатом.
        :return: True, если попытку нужно повторить.
        """
        if not isinstance(error, self._expected_exceptions):
            return False
        if self._retry_on_exception is None:
            return True
        return self._retry_on_exception(error)

    def record_result(self, value: T | None) -> None:
        """Сохранить результат попытки.

        :param value: значение, которое вернул предикат.
        """
        self._last_result = value
        self._last_exception = None
        self._is_satisfied = self._succeeds_on(value)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Ожидание %s: попытка %d вернула %s",
                self._waiting_for,
                self._attempts,
                safe_repr(value),
            )

    def record_exception(self, error: Exception) -> None:
        """Сохранить ожидаемое исключение попытки.

        :param error: исключение, выброшенное предикатом.
        """
        self._last_result = None
        self._last_exception = error
        self._is_satisfied = False
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Ожидание %s: попытка %d завершилась ожидаемым %s: %s",
                self._waiting_for,
                self._attempts,
                type(error).__name__,
                safe_str(error),
            )

    def next_delay(self) -> float | None:
        """Вычислить паузу перед следующей попыткой.

        :return: пауза в секундах или None, если ожидание нужно прекратить.
        """
        remaining = self._deadline.seconds_remaining()
        if remaining <= 0:
            self._stop_reason = STOP_ON_TIMEOUT
            return None
        if self._max_attempts is not None and self._attempts >= self._max_attempts:
            self._stop_reason = STOP_ON_ATTEMPTS
            return None
        delay = next(self._delays)
        if delay >= remaining:
            self._stop_reason = STOP_ON_NO_TIME
            return None
        return delay

    def build_attempt(self, *, next_sleep_seconds: float | None) -> Attempt:
        """Собрать описание последней попытки для передачи в хук.

        :param next_sleep_seconds: пауза перед следующей попыткой или None, если её не будет.
        :return: описание попытки.
        """
        return self._attempt_at(self._deadline.elapsed_seconds(), next_sleep_seconds)

    def terminal_snapshot(self) -> tuple[WaitStoppedError, Attempt]:
        """Собрать согласованные ошибку остановки и описание последней попытки.

        Часы читаются один раз, поэтому оба объекта описывают ровно один момент времени.

        :return: пара из ошибки остановки и описания последней попытки.
        """
        elapsed = self._deadline.elapsed_seconds()
        if elapsed >= self._deadline.timeout_seconds:
            self._stop_reason = STOP_ON_TIMEOUT
        return self._stop_error_at(elapsed), self._attempt_at(elapsed, None)

    def _attempt_at(self, elapsed_seconds: float, next_sleep_seconds: float | None) -> Attempt:
        return Attempt(
            number=self._attempts,
            elapsed_seconds=elapsed_seconds,
            result=self._last_result,
            exception=self._last_exception,
            next_sleep_seconds=next_sleep_seconds,
        )

    def _stop_error_at(self, elapsed_seconds: float) -> WaitStoppedError:
        if self._stop_reason == STOP_ON_ATTEMPTS:
            return AttemptsExhaustedError(
                waiting_for=self._waiting_for,
                timeout_seconds=self._deadline.timeout_seconds,
                attempts=self._attempts,
                elapsed_seconds=elapsed_seconds,
                last_result=self._last_result,
                last_exception=self._last_exception,
            )
        return TimeoutExpiredError(
            waiting_for=self._waiting_for,
            timeout_seconds=self._deadline.timeout_seconds,
            attempts=self._attempts,
            elapsed_seconds=elapsed_seconds,
            last_result=self._last_result,
            last_exception=self._last_exception,
            deadline_reached=self._stop_reason == STOP_ON_TIMEOUT,
        )
