import inspect
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    AsyncExitStack,
    ExitStack,
    asynccontextmanager,
    contextmanager,
)
from functools import wraps
from typing import Literal, Protocol, cast, overload

from httpx import Response
from tenacity import AsyncRetrying, RetryCallState, Retrying

from ._types import is_http_response
from .config import RetryHookT
from .policy import RETRYABLE_EXCEPTIONS, ResponseCondition, RetryPolicy, set_rejected
from .request_body import body_rewinder
from .retry_after import wait_retry_after

__all__ = [
    "RETRYABLE_EXCEPTIONS",
    "async_retry_stream_if",
    "async_retry_stream_if_failed",
    "async_stream_decorator",
    "retry_if",
    "retry_if_failed",
    "retry_stream_if",
    "retry_stream_if_failed",
    "send_decorator",
    "stream_decorator",
]


def retry_if[**P, R](retry_condition: ResponseCondition) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a function to retry when retry_condition is met."""
    return send_decorator(RetryPolicy(conditions=[retry_condition]))


def retry_if_failed[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Decorate a function to retry requests on server connection errors.

    Preserve the original exception: `reraise=True` raises it again,
    while `reraise=False` exposes it through `RetryError.last_attempt.exception()`.
    """
    return send_decorator(RetryPolicy(retry_on_network_errors=True))(func)


def retry_stream_if_failed[**P](
    func: Callable[P, AbstractContextManager[Response]],
) -> Callable[P, AbstractContextManager[Response]]:
    """Streaming request decorator that retries opening a stream on connection errors."""
    return stream_decorator(RetryPolicy(retry_on_network_errors=True))(func)


def retry_stream_if[**P](
    retry_condition: ResponseCondition,
) -> Callable[[Callable[P, AbstractContextManager[Response]]], Callable[P, AbstractContextManager[Response]]]:
    """Streaming request decorator for retries when retry_condition is met."""
    return stream_decorator(RetryPolicy(conditions=[retry_condition]))


def async_retry_stream_if_failed[**P](
    func: Callable[P, AbstractAsyncContextManager[Response]],
) -> Callable[P, AbstractAsyncContextManager[Response]]:
    """Asynchronous version of :func:`retry_stream_if_failed`."""
    return async_stream_decorator(RetryPolicy(retry_on_network_errors=True))(func)


def async_retry_stream_if[**P](
    retry_condition: ResponseCondition,
) -> Callable[[Callable[P, AbstractAsyncContextManager[Response]]], Callable[P, AbstractAsyncContextManager[Response]]]:
    """Asynchronous version of :func:`retry_stream_if`."""
    return async_stream_decorator(RetryPolicy(conditions=[retry_condition]))


def send_decorator[**P, R](policy: RetryPolicy) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate the `send` method using the shared client policy."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if _is_async_callable(func):
            async_func = cast("Callable[P, Awaitable[object]]", func)
            return cast("Callable[P, R]", _async_send(async_func, policy))
        return _sync_send(func, policy)

    return decorator


def stream_decorator[**P](
    policy: RetryPolicy,
) -> Callable[[Callable[P, AbstractContextManager[Response]]], Callable[P, AbstractContextManager[Response]]]:
    """Decorate synchronous `stream_request`.

    Wrap context manager entry: the connection is established in `__enter__`,
    not at call time, so a regular stream decorator would not work.
    """

    def decorator(
        func: Callable[P, AbstractContextManager[Response]],
    ) -> Callable[P, AbstractContextManager[Response]]:
        @wraps(func)
        @contextmanager
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Iterator[Response]:
            rewind = body_rewinder(args, kwargs)
            if rewind is None:
                # A retry is impossible, but evaluate the condition and return the response unchanged.
                with func(*args, **kwargs) as response:
                    _evaluate_once(response, policy)
                    yield response
                return

            with ExitStack() as stack:
                # Forward arguments so before_sleep_hook can access the request
                # in retry_state.args.
                def open_stream(*call_args: P.args, **call_kwargs: P.kwargs) -> Response:
                    rewind()
                    stream = func(*call_args, **call_kwargs)
                    response = stream.__enter__()
                    try:
                        rejected = policy.rejects(response)
                    except BaseException:
                        # The user condition failed after the stream opened, so close it here.
                        stream.__exit__(*sys.exc_info())
                        raise

                    if rejected:
                        # Close immediately; otherwise the connection remains open until the outer with ends.
                        stream.__exit__(None, None, None)
                    else:
                        stack.push(stream)

                    set_rejected(response, rejected=rejected)

                    return response

                yield _retrying(policy, is_async=False)(open_stream, *args, **kwargs)

        return wrapper

    return decorator


def async_stream_decorator[**P](
    policy: RetryPolicy,
) -> Callable[[Callable[P, AbstractAsyncContextManager[Response]]], Callable[P, AbstractAsyncContextManager[Response]]]:
    """Decorate asynchronous `stream_request`."""

    def decorator(
        func: Callable[P, AbstractAsyncContextManager[Response]],
    ) -> Callable[P, AbstractAsyncContextManager[Response]]:
        @wraps(func)
        @asynccontextmanager
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[Response]:
            rewind = body_rewinder(args, kwargs)
            if rewind is None:
                async with func(*args, **kwargs) as response:
                    await _evaluate_once_async(response, policy)
                    yield response
                return

            async with AsyncExitStack() as stack:

                async def open_stream(*call_args: P.args, **call_kwargs: P.kwargs) -> Response:
                    rewind()
                    stream = func(*call_args, **call_kwargs)
                    response = await stream.__aenter__()
                    try:
                        rejected = policy.rejects(response)
                    except BaseException:
                        await stream.__aexit__(*sys.exc_info())
                        raise

                    if rejected:
                        await stream.__aexit__(None, None, None)
                    else:
                        stack.push_async_exit(stream)

                    set_rejected(response, rejected=rejected)

                    return response

                yield await _retrying(policy, is_async=True)(open_stream, *args, **kwargs)

        return wrapper

    return decorator


def _sync_send[**P, R](func: Callable[P, R], policy: RetryPolicy) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        rewind = body_rewinder(args, kwargs)
        if rewind is None:
            # The request body cannot be resent: a retry would silently corrupt data.
            # Still evaluate the condition once and return the response unchanged to the caller.
            result = func(*args, **kwargs)
            _evaluate_once(result, policy)

            return result

        def attempt(*call_args: P.args, **call_kwargs: P.kwargs) -> R:
            rewind()
            result = func(*call_args, **call_kwargs)
            _reject(result, policy)

            return result

        return _retrying(policy, is_async=False)(attempt, *args, **kwargs)

    return wrapper


def _async_send[**P, R](func: Callable[P, Awaitable[R]], policy: RetryPolicy) -> Callable[P, Awaitable[R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        rewind = body_rewinder(args, kwargs)
        if rewind is None:
            result = await func(*args, **kwargs)
            await _evaluate_once_async(result, policy)

            return result

        async def attempt(*call_args: P.args, **call_kwargs: P.kwargs) -> R:
            rewind()
            result = await func(*call_args, **call_kwargs)
            await _reject_async(result, policy)

            return result

        return await _retrying(policy, is_async=True)(attempt, *args, **kwargs)

    return wrapper


def _reject(result: object, policy: RetryPolicy) -> None:
    """Mark a rejected response and release its connection."""
    if not is_http_response(result):
        return

    rejected = _ask_policy(result, policy)
    if rejected and not result.is_closed:
        # send(stream=True) returns an unread response: without close(), the connection leaks.
        result.close()

    set_rejected(result, rejected=rejected)


async def _reject_async(result: object, policy: RetryPolicy) -> None:
    if not is_http_response(result):
        return

    rejected = await _ask_policy_async(result, policy)
    if rejected and not result.is_closed:
        await result.aclose()

    set_rejected(result, rejected=rejected)


def _evaluate_once(result: object, policy: RetryPolicy) -> None:
    """Evaluate the condition without touching the response: the request cannot be retried anyway."""
    if is_http_response(result):
        _ask_policy(result, policy)


async def _evaluate_once_async(result: object, policy: RetryPolicy) -> None:
    if is_http_response(result):
        await _ask_policy_async(result, policy)


def _ask_policy(response: Response, policy: RetryPolicy) -> bool:
    """Evaluate the user condition and close the response if it fails."""
    try:
        return policy.rejects(response)
    except BaseException:
        if not response.is_closed:
            response.close()
        raise


async def _ask_policy_async(response: Response, policy: RetryPolicy) -> bool:
    try:
        return policy.rejects(response)
    except BaseException:
        if not response.is_closed:
            await response.aclose()
        raise


def _is_async_callable(func: object) -> bool:
    if inspect.iscoroutinefunction(func):
        return True

    call = cast("object", getattr(func, "__call__", None))  # noqa: B004 - Hook object with async def __call__

    return call is not None and inspect.iscoroutinefunction(call)


def _reject_async_hook(hook: RetryHookT) -> None:
    message = (
        f"before_sleep_hook {hook!r} асинхронный, а клиент синхронный — такой хук не будет вызван. "
        "Передайте синхронную функцию либо используйте AsyncHttpClient."
    )
    raise TypeError(message)


def _sync_hook(hook: RetryHookT | None) -> Callable[[RetryCallState], None] | None:
    """Prepare a hook for a synchronous retry loop.

    Synchronous `tenacity.Retrying` does not await hook results: a coroutine will not run,
    causing `never awaited`. Reject asynchronous hooks immediately; reject a regular function
    that returns an awaitable when it returns, since the hook type allows it.
    """
    if hook is None:
        return None

    if _is_async_callable(hook):
        _reject_async_hook(hook)

    @wraps(hook)
    def guarded(retry_state: RetryCallState) -> None:
        result = hook(retry_state)
        if not inspect.isawaitable(result):
            return

        close = cast("Callable[[], object] | None", getattr(result, "close", None))
        if callable(close):
            close()

        _reject_async_hook(hook)
        return

    return guarded


class _SyncRetry(Protocol):
    def __call__[**P, R](self, function: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R: ...


class _AsyncRetry(Protocol):
    def __call__[**P, R](
        self, function: Callable[P, Awaitable[R]], *args: P.args, **kwargs: P.kwargs
    ) -> Awaitable[R]: ...


@overload
def _retrying(policy: RetryPolicy, *, is_async: Literal[False]) -> _SyncRetry: ...


@overload
def _retrying(policy: RetryPolicy, *, is_async: Literal[True]) -> _AsyncRetry: ...


def _retrying(policy: RetryPolicy, *, is_async: bool) -> _SyncRetry | _AsyncRetry:
    cfg = policy.resolve_config()
    wait = wait_retry_after(cfg.wait, cfg.max_retry_after) if cfg.respect_retry_after else cfg.wait
    if is_async:
        return cast(
            "_AsyncRetry",
            AsyncRetrying(
                wait=wait,
                stop=cfg.stop,
                retry=policy.build_strategy(),
                before_sleep=cfg.before_sleep_hook,
                reraise=cfg.reraise,
            ),
        )
    return cast(
        "_SyncRetry",
        Retrying(
            wait=wait,
            stop=cfg.stop,
            retry=policy.build_strategy(),
            before_sleep=_sync_hook(cfg.before_sleep_hook),
            reraise=cfg.reraise,
        ),
    )
