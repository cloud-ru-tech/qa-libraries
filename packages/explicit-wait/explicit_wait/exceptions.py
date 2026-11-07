from __future__ import annotations

import logging
from collections.abc import Callable
from typing import NotRequired, TypedDict, Unpack, cast

MAX_RESULT_REPR_LENGTH = 200

logger = logging.getLogger(__name__)

type ErrorReducer = Callable[[type[WaitError], tuple[object, ...], dict[str, object]], WaitError]
type ErrorState = tuple[type[WaitError], tuple[object, ...], dict[str, object]]


class WaitFailureDetails(TypedDict):
    """Диагностика ожидания, остановленного до выполнения условия."""

    waiting_for: str
    timeout_seconds: float
    attempts: int
    elapsed_seconds: float
    last_result: NotRequired[object]
    last_exception: NotRequired[Exception | None]


class WaitError(Exception):
    """Базовая ошибка библиотеки явных ожиданий."""

    def __reduce__(self) -> tuple[ErrorReducer, ErrorState]:
        """Восстановить исключение целиком: аргументы, поля и заметки.

        Конструктор подкласса не вызывается, поэтому переопределённая сигнатура и
        обязательные поля пользовательских наследников не мешают десериализации.
        """
        return (
            _rebuild_error,
            (type(self), cast("tuple[object, ...]", self.args), cast("dict[str, object]", self.__dict__).copy()),
        )


class InvalidPredicateError(WaitError, TypeError):
    """Предикат нарушил контракт синхронного ожидания.

    Наследуется от ``TypeError``, чтобы вызывающий код мог ловить ошибку привычным способом,
    и от ``WaitError``, чтобы её не мог поглотить ``expected_exceptions``.
    """


class WaitStoppedError(WaitError):
    """Ожидание прекращено, так и не дождавшись выполнения условия.

    Несёт диагностику последней попытки, чтобы упавший автотест объяснял причину сам.
    """

    def __init__(self, **details: Unpack[WaitFailureDetails]) -> None:
        """Сохранить диагностику последней попытки.

        :param details: описание ожидания и его последнего результата.
        """
        self.waiting_for = details["waiting_for"]
        self.timeout_seconds = details["timeout_seconds"]
        self.attempts = details["attempts"]
        self.elapsed_seconds = details["elapsed_seconds"]
        self.last_result = details.get("last_result")
        self.last_exception = details.get("last_exception")
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        parts = [
            f"{self._reason()} waiting for {self.waiting_for}",
            f"attempts: {self.attempts}",
            f"elapsed: {self.elapsed_seconds:.3f}s",
        ]
        if self.last_exception is not None:
            parts.append(f"last exception: {type(self.last_exception).__name__}: {safe_str(self.last_exception)}")
        else:
            parts.append(f"last result: {self._last_result_repr()}")
        return f"{parts[0]} ({', '.join(parts[1:])})"

    def _reason(self) -> str:
        return "Wait stopped"

    def _last_result_repr(self) -> str:
        text = safe_repr(self.last_result)
        if len(text) <= MAX_RESULT_REPR_LENGTH:
            return text
        return f"{text[:MAX_RESULT_REPR_LENGTH]}... (truncated)"


class TimeoutExpiredError(WaitStoppedError, TimeoutError):
    """Ожидание прекращено по времени.

    Наследуется от встроенного ``TimeoutError``, чтобы таймауты этой библиотеки и таймауты
    ``asyncio`` ловились одним ``except``. Обратите внимание, что ``httpx.TimeoutException``
    в эту иерархию не входит и требует отдельного перехвата.

    Флаг ``deadline_reached`` различает две ситуации: дедлайн действительно наступил либо
    очередная пауза в него уже не помещалась и начинать новую попытку было бессмысленно.
    """

    def __init__(self, *, deadline_reached: bool = True, **details: Unpack[WaitFailureDetails]) -> None:
        """Сохранить диагностику остановки по времени.

        :param deadline_reached: наступил ли дедлайн фактически.
        :param details: описание ожидания и его последнего результата.
        """
        self.deadline_reached = deadline_reached
        super().__init__(**details)

    def _reason(self) -> str:
        if self.deadline_reached:
            return f"Timeout of {self.timeout_seconds} seconds expired"
        return f"No further attempt could start before the {self.timeout_seconds} second deadline"


class AttemptsExhaustedError(WaitStoppedError):
    """Исчерпано максимальное число попыток, заданное параметром ``max_attempts``."""

    def _reason(self) -> str:
        return f"All {self.attempts} attempts exhausted"


class WaitCancelledError(WaitError):
    """Ожидание прервано извне через ``cancel_event``."""

    def __init__(self, *, waiting_for: str, attempts: int, elapsed_seconds: float) -> None:
        """Инициализировать объект.

        :param waiting_for: значение настройки ``waiting_for``.
        :param attempts: значение настройки ``attempts``.
        :param elapsed_seconds: значение настройки ``elapsed_seconds``.
        """
        self.waiting_for = waiting_for
        self.attempts = attempts
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"Wait for {waiting_for} cancelled (attempts: {attempts}, elapsed: {elapsed_seconds:.3f}s)",
        )


def safe_repr(value: object) -> str:
    """Получить repr значения, не позволяя ему подменить исходную ошибку.

    :param value: произвольный объект, ``__repr__`` которого может выбросить исключение.
    :return: repr объекта либо пометка о сбое.
    """
    try:
        return repr(value)
    except Exception as error:
        logger.debug("Не удалось получить repr результата", exc_info=True)
        return f"<repr failed: {type(error).__name__}>"


def safe_str(value: object) -> str:
    """Получить строковое представление, не позволяя ему подменить исходную ошибку.

    :param value: произвольный объект, ``__str__`` которого может выбросить исключение.
    :return: строковое представление объекта либо пометка о сбое.
    """
    try:
        return str(value)
    except Exception as error:
        logger.debug("Не удалось получить строку результата", exc_info=True)
        return f"<str failed: {type(error).__name__}>"


def _rebuild_error(
    error_class: type[WaitError],
    args: tuple[object, ...],
    state: dict[str, object],
) -> WaitError:
    error = error_class.__new__(error_class)
    BaseException.__init__(error, *args)
    cast("dict[str, object]", error.__dict__).update(state)
    return error
