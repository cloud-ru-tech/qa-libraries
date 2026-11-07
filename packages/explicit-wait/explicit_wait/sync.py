import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import TypeVar

from .attempt import Attempt
from .config import WaitOptions
from .exceptions import WaitCancelledError, WaitError, WaitStoppedError
from .loop import WaitLoop, describe_predicate
from .types import Clock, Sleeper
from .validators import reject_awaitable

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _DriverOptions:
    alternative: str
    sleeper: Sleeper
    cancel_event: Event | None


def wait_until[T](
    predicate: Callable[[], T | None],
    *,
    options: WaitOptions | None = None,
    cancel_event: Event | None = None,
    clock: Clock = time.monotonic,
    sleeper: Sleeper = time.sleep,
) -> T:
    """Ожидать, пока предикат не вернёт значение, отличное от falsy.

    Первая попытка выполняется всегда. Повторная попытка выполняется только если её
    успеваем начать до дедлайна; сам предикат при наступлении дедлайна не прерывается.

    :param predicate: функция-предикат.
    :param options: параметры ожидания; None использует значения по умолчанию.
    :param cancel_event: событие отмены; когда задано, пауза выполняется через него,
        поэтому параметр ``sleeper`` не используется.
    :param clock: источник монотонного времени.
    :param sleeper: функция сна между попытками.
    :return: значение, которое вернул предикат.
    :raises TimeoutExpiredError: если истекло время ожидания.
    :raises AttemptsExhaustedError: если исчерпаны попытки, заданные ``max_attempts``.
    :raises WaitCancelledError: если ожидание отменено через ``cancel_event``.
    :raises InvalidPredicateError: если предикат вернул awaitable: объект корутины всегда
        truthy и завершил бы ожидание «успешно», не выполнив тело предиката.
        Для корутинного предиката предназначена ``async_wait_until``.
    """
    options = WaitOptions() if options is None else options
    loop = _build_loop(
        predicate,
        options=options,
        succeeds_on=bool,
        clock=clock,
    )
    error = _drive(
        loop,
        predicate,
        runtime=_DriverOptions("async_wait_until", sleeper, cancel_event),
        options=options,
    )
    if error is not None:
        raise error from error.last_exception
    return loop.value


def wait_or_none[T](
    predicate: Callable[[], T | None],
    *,
    options: WaitOptions | None = None,
    cancel_event: Event | None = None,
    clock: Clock = time.monotonic,
    sleeper: Sleeper = time.sleep,
) -> T | None:
    """Ожидать, пока предикат не вернёт значение, отличное от falsy, и вернуть None при неудаче.

    Ошибка остановки не перехватывается по типу, поэтому ``TimeoutExpiredError``,
    выброшенный самим предикатом или вложенным ожиданием, не будет проглочен.

    :param predicate: функция-предикат.
    :param options: параметры ожидания; None использует значения по умолчанию.
    :param cancel_event: событие отмены; когда задано, пауза выполняется через него,
        поэтому параметр ``sleeper`` не используется.
    :param clock: источник монотонного времени.
    :param sleeper: функция сна между попытками.
    :return: значение, которое вернул предикат, либо None если дождаться не удалось.
    :raises WaitCancelledError: если ожидание отменено через ``cancel_event``.
    :raises InvalidPredicateError: если предикат вернул awaitable: объект корутины всегда
        truthy и завершил бы ожидание «успешно», не выполнив тело предиката.
        Для корутинного предиката предназначена ``async_wait_or_none``.
    """
    options = WaitOptions() if options is None else options
    loop = _build_loop(
        predicate,
        options=options,
        succeeds_on=bool,
        clock=clock,
    )
    error = _drive(
        loop,
        predicate,
        runtime=_DriverOptions("async_wait_or_none", sleeper, cancel_event),
        options=options,
    )
    return None if error is not None else loop.value


def wait_while(
    predicate: Callable[[], object],
    *,
    options: WaitOptions | None = None,
    cancel_event: Event | None = None,
    clock: Clock = time.monotonic,
    sleeper: Sleeper = time.sleep,
) -> None:
    """Ожидать, пока предикат не перестанет возвращать truthy-значение.

    :param predicate: функция-предикат.
    :param options: параметры ожидания; None использует значения по умолчанию.
    :param cancel_event: событие отмены; когда задано, пауза выполняется через него,
        поэтому параметр ``sleeper`` не используется.
    :param clock: источник монотонного времени.
    :param sleeper: функция сна между попытками.
    :raises TimeoutExpiredError: если истекло время ожидания.
    :raises AttemptsExhaustedError: если исчерпаны попытки, заданные ``max_attempts``.
    :raises WaitCancelledError: если ожидание отменено через ``cancel_event``.
    :raises InvalidPredicateError: если предикат вернул awaitable: объект корутины всегда
        truthy и ожидание не закончилось бы никогда, не выполнив тело предиката.
        Для корутинного предиката предназначена ``async_wait_while``.
    """
    options = WaitOptions() if options is None else options
    loop = _build_loop(
        predicate,
        options=options,
        succeeds_on=_is_falsy,
        clock=clock,
    )
    error = _drive(
        loop,
        predicate,
        runtime=_DriverOptions("async_wait_while", sleeper, cancel_event),
        options=options,
    )
    if error is not None:
        raise error from error.last_exception


def _is_falsy(value: object) -> bool:
    return not value


def _build_loop[T](
    predicate: Callable[[], T | None],
    *,
    options: WaitOptions,
    succeeds_on: Callable[[object], bool],
    clock: Clock,
) -> WaitLoop[T]:
    return WaitLoop[T](
        waiting_for=describe_predicate(predicate, options.message),
        options=options,
        succeeds_on=succeeds_on,
        clock=clock,
    )


def _drive[T](
    loop: WaitLoop[T],
    predicate: Callable[[], T | None],
    *,
    runtime: _DriverOptions,
    options: WaitOptions,
) -> WaitStoppedError | None:
    while True:
        _raise_if_cancelled(loop, runtime.cancel_event)
        if loop.attempts > 0 and loop.expire_if_deadline_reached():
            return _stop(loop, options.on_timeout, options.on_attempts_exhausted, runtime.cancel_event)

        _run_attempt(loop, predicate, runtime.alternative)
        delay = None if loop.is_satisfied else loop.next_delay()
        if options.on_attempt is not None:
            options.on_attempt(loop.build_attempt(next_sleep_seconds=delay))

        _raise_if_cancelled(loop, runtime.cancel_event)
        if loop.is_satisfied:
            return None
        deadline_reached = loop.expire_if_deadline_reached()
        if deadline_reached or delay is None:
            return _stop(loop, options.on_timeout, options.on_attempts_exhausted, runtime.cancel_event)
        _sleep(loop, delay, sleeper=runtime.sleeper, cancel_event=runtime.cancel_event)


def _run_attempt[T](loop: WaitLoop[T], predicate: Callable[[], T | None], alternative: str) -> None:
    loop.start_attempt()
    try:
        value = predicate()
    except WaitError:
        raise
    except Exception as error:
        if not loop.is_expected(error):
            raise
        loop.record_exception(error)
        return
    # Проверка вне try: её TypeError не должен попасть под expected_exceptions.
    reject_awaitable(value, alternative=alternative)
    loop.record_result(value)


def _stop[T](
    loop: WaitLoop[T],
    on_timeout: Callable[[Attempt], None] | None,
    on_attempts_exhausted: Callable[[Attempt], None] | None,
    cancel_event: Event | None,
) -> WaitStoppedError:
    _raise_if_cancelled(loop, cancel_event)
    error, attempt = loop.terminal_snapshot()
    hook = on_attempts_exhausted if loop.stopped_on_attempts else on_timeout
    if hook is not None:
        hook(attempt)
    return error


def _sleep[T](
    loop: WaitLoop[T],
    delay: float,
    *,
    sleeper: Sleeper,
    cancel_event: Event | None,
) -> None:
    if cancel_event is None:
        sleeper(delay)
        return
    if cancel_event.wait(delay):
        raise _cancelled_error(loop)


def _raise_if_cancelled[T](loop: WaitLoop[T], cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise _cancelled_error(loop)


def _cancelled_error[T](loop: WaitLoop[T]) -> WaitCancelledError:
    return WaitCancelledError(
        waiting_for=loop.waiting_for,
        attempts=loop.attempts,
        elapsed_seconds=loop.elapsed_seconds(),
    )
