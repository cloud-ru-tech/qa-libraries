"""Декораторы транспорта: метрики send и трассировка stream_request.

Декораторы оборачивают send/stream_request, поэтому видят запрос на выходе
и ответ на входе. Один вызов send — это одна попытка транспорта: редиректы
httpx проходит внутри неё, так что счётчик покажет один вызов, а лог — все
запросы цепочки.

Для AsyncHttpClient декоратор обязан быть асинхронным: автоматической обёртки,
как у хуков, здесь нет — отсюда пары sync/async.
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
    """Счётчики, которые набивают декораторы send."""

    by_method: Counter[str] = field(default_factory=Counter)
    by_status: Counter[int] = field(default_factory=Counter)
    failures: int = 0
    total_elapsed_ms: float = 0.0

    @property
    def calls(self) -> int:
        """Сколько раз был вызван транспорт."""
        return sum(self.by_method.values())

    def record_success(self, method: str, status_code: int, elapsed_ms: float) -> None:
        """Учесть успешную попытку транспорта."""
        self.by_method[method] += 1
        self.by_status[status_code] += 1
        self.total_elapsed_ms += elapsed_ms

    def record_failure(self, method: str) -> None:
        """Учесть попытку транспорта, завершившуюся исключением."""
        self.by_method[method] += 1
        self.failures += 1

    def summary(self) -> str:
        """Собрать итоговую строку метрик."""
        average_ms = self.total_elapsed_ms / self.calls if self.calls else 0.0
        by_method = ", ".join(f"{method}={count}" for method, count in sorted(self.by_method.items()))
        by_status = ", ".join(f"{status}={count}" for status, count in sorted(self.by_status.items()))
        return (
            f"вызовов send={self.calls}, ошибок={self.failures}, среднее время={average_ms:.1f} мс; "
            f"по методам: {by_method}; по статусам: {by_status}"
        )


def metrics_decorator(metrics: TransportMetrics, logger: Logger) -> SyncSendDecorator:
    """Собрать синхронный декоратор send, снимающий метрики.

    :param metrics: счётчики, которые нужно наполнять
    :param logger: логгер для строки метрики на каждый вызов
    :returns: декоратор метода send
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
    """Собрать асинхронный декоратор send, снимающий метрики.

    :param metrics: счётчики, которые нужно наполнять
    :param logger: логгер для строки метрики на каждый вызов
    :returns: декоратор асинхронного метода send
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
    """Собрать синхронный декоратор stream_request, отмечающий время жизни потока.

    Тело потокового ответа в лог не попадает — на момент хука оно ещё не прочитано,
    поэтому длительность чтения видно только отсюда.

    :param logger: логгер для отметок открытия и закрытия потока
    :returns: декоратор метода stream_request
    """

    def decorator(func: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        # @contextmanager обязан быть ниже @wraps: декоратор stream_request
        # должен вернуть контекстный менеджер, а не генератор.
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
    """Собрать асинхронный декоратор stream_request, отмечающий время жизни потока.

    :param logger: логгер для отметок открытия и закрытия потока
    :returns: декоратор асинхронного метода stream_request
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
