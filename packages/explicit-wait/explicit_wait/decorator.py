import asyncio
import functools
import inspect
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import replace
from typing import ParamSpec, TypeVar, cast

from .aio import async_wait_until
from .config import WaitOptions
from .exceptions import InvalidPredicateError
from .sync import wait_until
from .types import AsyncSleeper, Clock, Sleeper

P = ParamSpec("P")
T = TypeVar("T")


def wait_for(
    *,
    options: WaitOptions | None = None,
    clock: Clock = time.monotonic,
    sleeper: Sleeper = time.sleep,
) -> Callable[[Callable[P, T | None]], Callable[P, T]]:
    """Wrap a function to wait for its first truthy result.

    The decorated function is called repeatedly until success, so it can be used
    as a regular call without wrapping it in a lambda each time.

    :param options: wait parameters; None uses the defaults.
    :param clock: monotonic time source.
    :param sleeper: sleep function between attempts.
    :return: synchronous function decorator.
    :raises InvalidPredicateError: if decorating a coroutine function.
    """

    def decorator(function: Callable[P, T | None]) -> Callable[P, T]:
        if inspect.iscoroutinefunction(cast("object", function)):
            rejection = (
                f"{function.__qualname__} is a coroutine function and cannot be awaited by a "
                "synchronous wait; use async_wait_for instead"
            )
            raise InvalidPredicateError(rejection)

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return wait_until(
                lambda: function(*args, **kwargs),
                options=replace(
                    WaitOptions() if options is None else options,
                    message=options.message
                    if options is not None and options.message is not None
                    else function.__qualname__,
                ),
                clock=clock,
                sleeper=sleeper,
            )

        return wrapper

    return decorator


def async_wait_for(
    *,
    options: WaitOptions | None = None,
    clock: Clock = time.monotonic,
    sleeper: AsyncSleeper = asyncio.sleep,
) -> Callable[[Callable[P, Awaitable[T | None]]], Callable[P, Coroutine[None, None, T]]]:
    """Wrap a coroutine function to wait for its first truthy result.

    :param options: wait parameters; None uses the defaults.
    :param clock: monotonic time source.
    :param sleeper: asynchronous sleep function between attempts.
    :return: asynchronous function decorator.
    """

    def decorator(function: Callable[P, Awaitable[T | None]]) -> Callable[P, Coroutine[None, None, T]]:
        @functools.wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await async_wait_until(
                lambda: function(*args, **kwargs),
                options=replace(
                    WaitOptions() if options is None else options,
                    message=options.message
                    if options is not None and options.message is not None
                    else function.__qualname__,
                ),
                clock=clock,
                sleeper=sleeper,
            )

        return wrapper

    return decorator
