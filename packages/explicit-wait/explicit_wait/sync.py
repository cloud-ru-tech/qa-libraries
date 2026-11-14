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
    """Wait until the predicate returns a non-falsy value.

    The first attempt always runs. A retry runs only if it can start before the deadline;
    the predicate itself is not interrupted when the deadline passes.

    :param predicate: predicate function.
    :param options: wait parameters; None uses the defaults.
    :param cancel_event: cancellation event; when set, it handles pauses,
        so the ``sleeper`` parameter is not used.
    :param clock: monotonic time source.
    :param sleeper: sleep function between attempts.
    :return: value returned by the predicate.
    :raises TimeoutExpiredError: if the wait times out.
    :raises AttemptsExhaustedError: if ``max_attempts`` is exhausted.
    :raises WaitCancelledError: if the wait is canceled through ``cancel_event``.
    :raises InvalidPredicateError: if the predicate returns an awaitable: a coroutine object is
        always truthy and would satisfy the wait without running the predicate body.
        Use ``async_wait_until`` for coroutine predicates.
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
    """Wait until the predicate returns a non-falsy value, returning None on failure.

    The stopping error is not caught by type, so a ``TimeoutExpiredError``
    raised by the predicate or a nested wait is not swallowed.

    :param predicate: predicate function.
    :param options: wait parameters; None uses the defaults.
    :param cancel_event: cancellation event; when set, it handles pauses,
        so the ``sleeper`` parameter is not used.
    :param clock: monotonic time source.
    :param sleeper: sleep function between attempts.
    :return: predicate value, or None if the condition was not satisfied.
    :raises WaitCancelledError: if the wait is canceled through ``cancel_event``.
    :raises InvalidPredicateError: if the predicate returns an awaitable: a coroutine object is
        always truthy and would satisfy the wait without running the predicate body.
        Use ``async_wait_or_none`` for coroutine predicates.
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
    """Wait until the predicate stops returning a truthy value.

    :param predicate: predicate function.
    :param options: wait parameters; None uses the defaults.
    :param cancel_event: cancellation event; when set, it handles pauses,
        so the ``sleeper`` parameter is not used.
    :param clock: monotonic time source.
    :param sleeper: sleep function between attempts.
    :raises TimeoutExpiredError: if the wait times out.
    :raises AttemptsExhaustedError: if ``max_attempts`` is exhausted.
    :raises WaitCancelledError: if the wait is canceled through ``cancel_event``.
    :raises InvalidPredicateError: if the predicate returns an awaitable: a coroutine object is
        always truthy and would keep the wait running forever without running the predicate body.
        Use ``async_wait_while`` for coroutine predicates.
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
    # Check outside try so its TypeError cannot be caught by expected_exceptions.
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
