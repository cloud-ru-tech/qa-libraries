import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import TypedDict, TypeVar, Unpack, cast, overload

from .attempt import Attempt
from .config import WaitOptions
from .exceptions import WaitError, WaitStoppedError
from .loop import WaitLoop, describe_predicate
from .types import AsyncSleeper, Clock

T = TypeVar("T")


class _AsyncWaitOptions(TypedDict, total=False):
    """Execution parameters for asynchronous waits."""

    options: WaitOptions | None
    clock: Clock
    sleeper: AsyncSleeper


@overload
async def async_wait_until[T](
    predicate: Callable[[], Awaitable[T | None]],
    **options: Unpack[_AsyncWaitOptions],
) -> T: ...


@overload
async def async_wait_until[T](
    predicate: Callable[[], Awaitable[T] | None],
    **options: Unpack[_AsyncWaitOptions],
) -> T: ...


@overload
async def async_wait_until[T](
    predicate: Callable[[], T | Awaitable[T] | None],
    **options: Unpack[_AsyncWaitOptions],
) -> T: ...


async def async_wait_until[T](
    predicate: Callable[[], T | Awaitable[T | None] | None],
    *,
    options: WaitOptions | None = None,
    clock: Clock = time.monotonic,
    sleeper: AsyncSleeper = asyncio.sleep,
) -> T:
    """Wait in the event loop until the predicate returns a non-falsy value.

    The predicate can be a coroutine or a regular function. Pauses between attempts
    do not block the event loop, so background tasks keep running. Cancel the wait
    through standard task cancellation: ``CancelledError`` is not caught.

    :param predicate: predicate function, possibly asynchronous.
    :param options: wait parameters; None uses the defaults.
    :param clock: monotonic time source.
    :param sleeper: asynchronous sleep function between attempts.
    :return: value returned by the predicate.
    :raises TimeoutExpiredError: if the wait times out.
    :raises AttemptsExhaustedError: if ``max_attempts`` is exhausted.
    """
    options = WaitOptions() if options is None else options
    loop = _build_loop(
        predicate,
        options=options,
        succeeds_on=bool,
        clock=clock,
    )
    error = await _drive(
        loop,
        predicate,
        sleeper=sleeper,
        options=options,
    )
    if error is not None:
        raise error from error.last_exception
    return loop.value


@overload
async def async_wait_or_none[T](
    predicate: Callable[[], Awaitable[T | None]],
    **options: Unpack[_AsyncWaitOptions],
) -> T | None: ...


@overload
async def async_wait_or_none[T](
    predicate: Callable[[], Awaitable[T] | None],
    **options: Unpack[_AsyncWaitOptions],
) -> T | None: ...


@overload
async def async_wait_or_none[T](
    predicate: Callable[[], T | Awaitable[T] | None],
    **options: Unpack[_AsyncWaitOptions],
) -> T | None: ...


async def async_wait_or_none[T](
    predicate: Callable[[], T | Awaitable[T | None] | None],
    *,
    options: WaitOptions | None = None,
    clock: Clock = time.monotonic,
    sleeper: AsyncSleeper = asyncio.sleep,
) -> T | None:
    """Wait in the event loop and return None if the condition is not satisfied.

    The stopping error is not caught by type, so a ``TimeoutExpiredError``
    raised by the predicate or a nested wait is not swallowed.

    :param predicate: predicate function, possibly asynchronous.
    :param options: wait parameters; None uses the defaults.
    :param clock: monotonic time source.
    :param sleeper: asynchronous sleep function between attempts.
    :return: predicate value, or None if the condition was not satisfied.
    """
    options = WaitOptions() if options is None else options
    loop = _build_loop(
        predicate,
        options=options,
        succeeds_on=bool,
        clock=clock,
    )
    error = await _drive(
        loop,
        predicate,
        sleeper=sleeper,
        options=options,
    )
    return None if error is not None else loop.value


async def async_wait_while(
    predicate: Callable[[], object] | Callable[[], Awaitable[object]],
    *,
    options: WaitOptions | None = None,
    clock: Clock = time.monotonic,
    sleeper: AsyncSleeper = asyncio.sleep,
) -> None:
    """Wait in the event loop until the predicate stops returning a truthy value.

    :param predicate: predicate function, possibly asynchronous.
    :param options: wait parameters; None uses the defaults.
    :param clock: monotonic time source.
    :param sleeper: asynchronous sleep function between attempts.
    :raises TimeoutExpiredError: if the wait times out.
    :raises AttemptsExhaustedError: if ``max_attempts`` is exhausted.
    """
    options = WaitOptions() if options is None else options
    loop = _build_loop(
        predicate,
        options=options,
        succeeds_on=_is_falsy,
        clock=clock,
    )
    error = await _drive(
        loop,
        predicate,
        sleeper=sleeper,
        options=options,
    )
    if error is not None:
        raise error from error.last_exception


def _is_falsy(value: object) -> bool:
    return not value


def _build_loop[T](
    predicate: Callable[[], T | Awaitable[T | None] | None],
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


async def _drive[T](
    loop: WaitLoop[T],
    predicate: Callable[[], T | Awaitable[T | None] | None],
    *,
    sleeper: AsyncSleeper,
    options: WaitOptions,
) -> WaitStoppedError | None:
    while True:
        if loop.attempts > 0 and loop.expire_if_deadline_reached():
            return _stop(loop, options.on_timeout, options.on_attempts_exhausted)

        await _run_attempt(loop, predicate)
        delay = None if loop.is_satisfied else loop.next_delay()
        if options.on_attempt is not None:
            options.on_attempt(loop.build_attempt(next_sleep_seconds=delay))

        if loop.is_satisfied:
            return None
        deadline_reached = loop.expire_if_deadline_reached()
        if deadline_reached or delay is None:
            return _stop(loop, options.on_timeout, options.on_attempts_exhausted)
        await sleeper(delay)


async def _run_attempt[T](
    loop: WaitLoop[T],
    predicate: Callable[[], T | Awaitable[T | None] | None],
) -> None:
    loop.start_attempt()
    try:
        value = await _call(predicate)
    except WaitError:
        raise
    except Exception as error:
        if not loop.is_expected(error):
            raise
        loop.record_exception(error)
    else:
        loop.record_result(value)


def _stop[T](
    loop: WaitLoop[T],
    on_timeout: Callable[[Attempt], None] | None,
    on_attempts_exhausted: Callable[[Attempt], None] | None,
) -> WaitStoppedError:
    error, attempt = loop.terminal_snapshot()
    hook = on_attempts_exhausted if loop.stopped_on_attempts else on_timeout
    if hook is not None:
        hook(attempt)
    return error


async def _call[T](predicate: Callable[[], T | Awaitable[T | None] | None]) -> T | None:
    result = predicate()
    if inspect.isawaitable(result):
        return await cast("Awaitable[T | None]", result)
    return result
