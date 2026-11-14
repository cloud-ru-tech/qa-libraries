"""Transport decorators: send metrics and stream_request tracing.

Decorators wrap send/stream_request, so they see the outgoing request
and incoming response. One send call is one transport attempt: httpx follows
redirects within it, so the counter shows one call while the log shows every
request in the chain.

AsyncHttpClient requires asynchronous decorators: there is no automatic wrapping
as there is for hooks, hence the sync/async pairs.
"""

from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from logging import Logger

    from http_client.types import (
        AsyncSendDecorator,
        AsyncSendMethod,
        AsyncStreamRequestDecorator,
        AsyncStreamRequestMethod,
        SyncSendDecorator,
        SyncSendMethod,
        SyncStreamRequestDecorator,
        SyncStreamRequestMethod,
    )
    from httpx._types import AuthTypes


@dataclass
class TransportMetrics:
    """Counters updated by send decorators."""

    by_method: Counter[str] = field(default_factory=Counter)
    by_status: Counter[int] = field(default_factory=Counter)
    failures: int = 0
    total_elapsed_ms: float = 0.0

    @property
    def calls(self) -> int:
        """Return the number of transport calls."""
        return sum(self.by_method.values())

    def record_success(self, method: str, status_code: int, elapsed_ms: float) -> None:
        """Record a successful transport attempt."""
        self.by_method[method] += 1
        self.by_status[status_code] += 1
        self.total_elapsed_ms += elapsed_ms

    def record_failure(self, method: str) -> None:
        """Record a transport attempt that raised an exception."""
        self.by_method[method] += 1
        self.failures += 1

    def summary(self) -> str:
        """Build a metrics summary string."""
        average_ms = self.total_elapsed_ms / self.calls if self.calls else 0.0
        by_method = ", ".join(f"{method}={count}" for method, count in sorted(self.by_method.items()))
        by_status = ", ".join(f"{status}={count}" for status, count in sorted(self.by_status.items()))
        return (
            f"вызовов send={self.calls}, ошибок={self.failures}, среднее время={average_ms:.1f} мс; "
            f"по методам: {by_method}; по статусам: {by_status}"
        )


def metrics_decorator(metrics: TransportMetrics, logger: Logger) -> SyncSendDecorator:
    """Build a synchronous send decorator that collects metrics.

    :param metrics: Counters to update
    :param logger: Logger for a metrics line on each call
    :returns: Send method decorator
    """

    def decorator(func: SyncSendMethod) -> SyncSendMethod:
        @wraps(func)
        def wrapper(
            request: httpx.Request,
            *,
            stream: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
            anonymous: bool = False,
        ) -> httpx.Response:
            started_at = perf_counter()
            try:
                response = func(
                    request,
                    stream=stream,
                    auth=auth,
                    follow_redirects=follow_redirects,
                    anonymous=anonymous,
                )
            except httpx.HTTPError as error:
                metrics.record_failure(request.method)
                logger.warning(
                    "Метрика: %s %s -> %s",
                    request.method,
                    request.url.path,
                    type(error).__name__,
                )
                raise

            elapsed_ms = (perf_counter() - started_at) * 1000
            metrics.record_success(request.method, response.status_code, elapsed_ms)
            logger.info(
                "Метрика: %s %s -> %s за %.1f мс",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response

        return wrapper

    return decorator


def async_metrics_decorator(metrics: TransportMetrics, logger: Logger) -> AsyncSendDecorator:
    """Build an asynchronous send decorator that collects metrics.

    :param metrics: Counters to update
    :param logger: Logger for a metrics line on each call
    :returns: Asynchronous send method decorator
    """

    def decorator(func: AsyncSendMethod) -> AsyncSendMethod:
        @wraps(func)
        async def wrapper(
            request: httpx.Request,
            *,
            stream: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
            anonymous: bool = False,
        ) -> httpx.Response:
            started_at = perf_counter()
            try:
                response = await func(
                    request,
                    stream=stream,
                    auth=auth,
                    follow_redirects=follow_redirects,
                    anonymous=anonymous,
                )
            except httpx.HTTPError as error:
                metrics.record_failure(request.method)
                logger.warning(
                    "Метрика: %s %s -> %s",
                    request.method,
                    request.url.path,
                    type(error).__name__,
                )
                raise

            elapsed_ms = (perf_counter() - started_at) * 1000
            metrics.record_success(request.method, response.status_code, elapsed_ms)
            logger.info(
                "Метрика: %s %s -> %s за %.1f мс",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response

        return wrapper

    return decorator


def stream_trace_decorator(logger: Logger) -> SyncStreamRequestDecorator:
    """Build a synchronous stream_request decorator that measures the stream lifetime.

    A streaming response body is not logged because it has not been read when the hook runs,
    so its read duration can only be measured here.

    :param logger: Logger for stream open and close events
    :returns: Stream_request method decorator
    """

    def decorator(func: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        # @contextmanager must be below @wraps: a stream_request decorator
        # must return a context manager rather than a generator.
        @wraps(func)
        @contextmanager
        def wrapper(
            request: httpx.Request,
            *,
            anonymous: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
        ) -> Iterator[httpx.Response]:
            started_at = perf_counter()
            logger.info("Поток открывается: %s %s", request.method, request.url.path)
            with func(request, anonymous=anonymous, auth=auth, follow_redirects=follow_redirects) as response:
                try:
                    yield response
                finally:
                    logger.info(
                        "Поток закрыт: %s %s -> %s, чтение заняло %.1f мс",
                        request.method,
                        request.url.path,
                        response.status_code,
                        (perf_counter() - started_at) * 1000,
                    )

        return wrapper

    return decorator


def async_stream_trace_decorator(logger: Logger) -> AsyncStreamRequestDecorator:
    """Build an asynchronous stream_request decorator that measures the stream lifetime.

    :param logger: Logger for stream open and close events
    :returns: Asynchronous stream_request method decorator
    """

    def decorator(func: AsyncStreamRequestMethod) -> AsyncStreamRequestMethod:
        @wraps(func)
        @asynccontextmanager
        async def wrapper(
            request: httpx.Request,
            *,
            anonymous: bool = False,
            auth: AuthTypes | None = None,
            follow_redirects: bool | None = None,
        ) -> AsyncIterator[httpx.Response]:
            started_at = perf_counter()
            logger.info("Поток открывается: %s %s", request.method, request.url.path)
            async with func(request, anonymous=anonymous, auth=auth, follow_redirects=follow_redirects) as response:
                try:
                    yield response
                finally:
                    logger.info(
                        "Поток закрыт: %s %s -> %s, чтение заняло %.1f мс",
                        request.method,
                        request.url.path,
                        response.status_code,
                        (perf_counter() - started_at) * 1000,
                    )

        return wrapper

    return decorator
