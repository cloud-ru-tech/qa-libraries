from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import Unpack, cast

import httpx
from assertpy import assert_that
from http_client.options import with_send_decorator, with_stream_decorator
from http_client.types import (
    AsyncSendDecorator,
    AsyncSendMethod,
    AsyncStreamRequestDecorator,
    AsyncStreamRequestMethod,
    SendOptions,
    StreamOptions,
    SyncSendDecorator,
    SyncSendMethod,
    SyncStreamRequestDecorator,
    SyncStreamRequestMethod,
)
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


def test_send_decorator_sees_sent_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Декоратор send получает отправляемый запрос."""
    seen: list[httpx.Request] = []

    def decorator(send: SyncSendMethod) -> SyncSendMethod:
        @wraps(send)
        def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            seen.append(request)
            return send(request, **kwargs)

        return wrapper

    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_send_decorator(decorator))
    request = httpx.Request("GET", "https://example.com/orders")

    client.send(request)

    assert_that(seen).is_equal_to([request])


def test_send_decorator_sees_received_response(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Декоратор send получает полученный ответ."""
    seen: list[int] = []

    def decorator(send: SyncSendMethod) -> SyncSendMethod:
        @wraps(send)
        def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            response = send(request, **kwargs)
            seen.append(response.status_code)
            return response

        return wrapper

    httpx_mock.add_response(status_code=202)
    client = new_client("https://example.com", with_send_decorator(decorator))

    client.send(httpx.Request("GET", "https://example.com/jobs"))

    assert_that(seen).is_equal_to([202])


def test_send_returns_response_through_decorator(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Ответ доходит до вызывающего кода сквозь декоратор."""
    payload: dict[str, bool] = {"queued": True}

    def decorator(send: SyncSendMethod) -> SyncSendMethod:
        @wraps(send)
        def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            return send(request, **kwargs)

        return wrapper

    httpx_mock.add_response(status_code=200, json=payload)
    client = new_client("https://example.com", with_send_decorator(decorator))

    response = client.send(httpx.Request("GET", "https://example.com/jobs"))

    assert_that(cast("object", response.json())).is_equal_to(payload)


def test_last_registered_send_decorator_wraps_the_others(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Декоратор, добавленный последним, оказывается самым внешним."""
    calls: list[str] = []

    def recording_decorator(name: str) -> SyncSendDecorator:
        def decorator(send: SyncSendMethod) -> SyncSendMethod:
            @wraps(send)
            def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
                calls.append(f"{name}_before")
                response = send(request, **kwargs)
                calls.append(f"{name}_after")
                return response

            return wrapper

        return decorator

    httpx_mock.add_response(status_code=200)
    client = new_client(
        "https://example.com",
        with_send_decorator(recording_decorator("inner")),
        with_send_decorator(recording_decorator("outer")),
    )

    client.send(httpx.Request("GET", "https://example.com/jobs"))

    assert_that(calls).is_equal_to(["outer_before", "inner_before", "inner_after", "outer_after"])


async def test_async_send_decorator_sees_sent_request(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Декоратор send асинхронного клиента получает отправляемый запрос."""
    seen: list[httpx.Request] = []

    def decorator(send: AsyncSendMethod) -> AsyncSendMethod:
        @wraps(send)
        async def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            seen.append(request)
            return await send(request, **kwargs)

        return wrapper

    httpx_mock.add_response(status_code=200)
    client = new_async_client("https://example.com", with_send_decorator(decorator))
    request = httpx.Request("GET", "https://example.com/orders")

    await client.send(request)

    assert_that(seen).is_equal_to([request])


async def test_async_send_returns_response_through_decorator(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Ответ асинхронного клиента доходит до вызывающего кода сквозь декоратор."""
    payload: dict[str, bool] = {"accepted": True}

    def decorator(send: AsyncSendMethod) -> AsyncSendMethod:
        @wraps(send)
        async def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            return await send(request, **kwargs)

        return wrapper

    httpx_mock.add_response(status_code=200, json=payload)
    client = new_async_client("https://example.com", with_send_decorator(decorator))

    response = await client.send(httpx.Request("GET", "https://example.com/orders"))

    assert_that(cast("object", response.json())).is_equal_to(payload)


async def test_async_send_decorator_runs_in_registration_order(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Асинхронный декоратор send, добавленный последним, оказывается самым внешним."""
    calls: list[str] = []

    def recording_decorator(name: str) -> AsyncSendDecorator:
        def decorator(send: AsyncSendMethod) -> AsyncSendMethod:
            @wraps(send)
            async def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
                calls.append(f"{name}_before")
                response = await send(request, **kwargs)
                calls.append(f"{name}_after")
                return response

            return wrapper

        return decorator

    httpx_mock.add_response(status_code=200)
    client = new_async_client(
        "https://example.com",
        with_send_decorator(recording_decorator("inner")),
        with_send_decorator(recording_decorator("outer")),
    )

    await client.send(httpx.Request("GET", "https://example.com/batches"))

    assert_that(calls).is_equal_to(["outer_before", "inner_before", "inner_after", "outer_after"])


def test_stream_decorator_sees_sent_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Декоратор stream_request получает отправляемый запрос."""
    seen: list[httpx.Request] = []

    def decorator(stream: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        @wraps(stream)
        @contextmanager
        def wrapper(request: httpx.Request, **kwargs: Unpack[StreamOptions]) -> Iterator[httpx.Response]:
            seen.append(request)
            with stream(request, **kwargs) as response:
                yield response

        return wrapper

    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_client("https://example.com", with_stream_decorator(decorator))
    request = httpx.Request("GET", "https://example.com/feed")

    with client.stream_request(request) as response:
        response.read()

    assert_that(seen).is_equal_to([request])


def test_stream_decorator_wraps_the_whole_context(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Декоратор stream_request охватывает всё время жизни потока."""
    calls: list[str] = []

    def decorator(stream: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        @wraps(stream)
        @contextmanager
        def wrapper(request: httpx.Request, **kwargs: Unpack[StreamOptions]) -> Iterator[httpx.Response]:
            calls.append("before")
            with stream(request, **kwargs) as response:
                calls.append("inside")
                yield response
            calls.append("after")

        return wrapper

    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_client("https://example.com", with_stream_decorator(decorator))

    with client.stream_request(httpx.Request("GET", "https://example.com/feed")) as response:
        calls.append("reading")
        response.read()

    assert_that(calls).is_equal_to(["before", "inside", "reading", "after"])


def test_last_registered_stream_decorator_wraps_the_others(
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Декоратор потока, добавленный последним, оказывается самым внешним."""
    calls: list[str] = []

    def recording_decorator(name: str) -> SyncStreamRequestDecorator:
        def decorator(stream: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
            @wraps(stream)
            @contextmanager
            def wrapper(request: httpx.Request, **kwargs: Unpack[StreamOptions]) -> Iterator[httpx.Response]:
                calls.append(f"{name}_before")
                with stream(request, **kwargs) as response:
                    yield response
                calls.append(f"{name}_after")

            return wrapper

        return decorator

    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_client(
        "https://example.com",
        with_stream_decorator(recording_decorator("inner")),
        with_stream_decorator(recording_decorator("outer")),
    )

    with client.stream_request(httpx.Request("GET", "https://example.com/feed")) as response:
        response.read()

    assert_that(calls).is_equal_to(["outer_before", "inner_before", "inner_after", "outer_after"])


async def test_async_stream_decorator_sees_sent_request(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Декоратор stream_request асинхронного клиента получает отправляемый запрос."""
    seen: list[httpx.Request] = []

    def decorator(stream: AsyncStreamRequestMethod) -> AsyncStreamRequestMethod:
        @wraps(stream)
        @asynccontextmanager
        async def wrapper(request: httpx.Request, **kwargs: Unpack[StreamOptions]) -> AsyncIterator[httpx.Response]:
            seen.append(request)
            async with stream(request, **kwargs) as response:
                yield response

        return wrapper

    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_async_client("https://example.com", with_stream_decorator(decorator))
    request = httpx.Request("GET", "https://example.com/feed")

    async with client.stream_request(request) as response:
        await response.aread()

    assert_that(seen).is_equal_to([request])


async def test_last_registered_async_stream_decorator_wraps_the_others(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Декоратор потока асинхронного клиента, добавленный последним, оказывается самым внешним."""
    calls: list[str] = []

    def recording_decorator(name: str) -> AsyncStreamRequestDecorator:
        def decorator(stream: AsyncStreamRequestMethod) -> AsyncStreamRequestMethod:
            @wraps(stream)
            @asynccontextmanager
            async def wrapper(
                request: httpx.Request,
                **kwargs: Unpack[StreamOptions],
            ) -> AsyncIterator[httpx.Response]:
                calls.append(f"{name}_before")
                async with stream(request, **kwargs) as response:
                    yield response
                calls.append(f"{name}_after")

            return wrapper

        return decorator

    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_async_client(
        "https://example.com",
        with_stream_decorator(recording_decorator("inner")),
        with_stream_decorator(recording_decorator("outer")),
    )

    async with client.stream_request(httpx.Request("GET", "https://example.com/feed")) as response:
        await response.aread()

    assert_that(calls).is_equal_to(["outer_before", "inner_before", "inner_after", "outer_after"])
