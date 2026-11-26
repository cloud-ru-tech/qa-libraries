from collections.abc import Iterator

import httpx2
import pytest
from assertpy import assert_that
from pytest_httpx2 import HTTPXMock, IteratorStream

from .support.clients import AsyncClientFactory, SyncClientFactory

EVENT_STREAM = {"Content-Type": "text/event-stream"}


def test_sse_sends_request_options(httpx2_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    client = new_client("https://example.com")
    _mock_subscription(httpx2_mock)

    with client.sse(
        "/events",
        method="POST",
        params={"topic": "build"},
        headers={"Last-Event-ID": "41", "cache-control": "no-cache"},
        json={"subscribed": True},
    ) as source:
        event = next(iter(source))

    assert_that(event).is_equal_to(httpx2.ServerSentEvent(event="build", id="42", data="ready"))


async def test_async_sse_sends_request_options(httpx2_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    client = new_async_client("https://example.com")
    _mock_subscription(httpx2_mock)

    async with client.sse(
        "/events",
        method="POST",
        params={"topic": "build"},
        headers={"Last-Event-ID": "41", "cache-control": "no-cache"},
        json={"subscribed": True},
    ) as source:
        event = await anext(aiter(source))

    assert_that(event).is_equal_to(httpx2.ServerSentEvent(event="build", id="42", data="ready"))


def test_sse_closes_after_first_event(httpx2_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    _mock_open_stream(httpx2_mock)
    client = new_client("https://example.com")

    with client.sse("/events") as source:
        next(iter(source))

    assert_that(source.response.is_closed).is_true()


async def test_async_sse_closes_after_first_event(httpx2_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    _mock_open_stream(httpx2_mock)
    client = new_async_client("https://example.com")

    async with client.sse("/events") as source:
        await anext(aiter(source))

    assert_that(source.response.is_closed).is_true()


@pytest.mark.parametrize(
    ("content_type", "error"),
    [("application/json", "content type"), ("text/event-stream", "byte limit")],
)
def test_sse_rejects_invalid_stream(
    httpx2_mock: HTTPXMock,
    new_client: SyncClientFactory,
    content_type: str,
    error: str,
) -> None:
    httpx2_mock.add_response(headers={"Content-Type": content_type}, content=b"data: too large\n\n")
    client = new_client("https://example.com")

    with client.sse("/events", max_event_size=4) as source, pytest.raises(httpx2.SSEError, match=error):
        next(iter(source))


@pytest.mark.parametrize(
    ("content_type", "error"),
    [("application/json", "content type"), ("text/event-stream", "byte limit")],
)
async def test_async_sse_rejects_invalid_stream(
    httpx2_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
    content_type: str,
    error: str,
) -> None:
    httpx2_mock.add_response(headers={"Content-Type": content_type}, content=b"data: too large\n\n")
    client = new_async_client("https://example.com")

    async with client.sse("/events", max_event_size=4) as source:
        with pytest.raises(httpx2.SSEError, match=error):
            await anext(aiter(source))


def _mock_subscription(httpx2_mock: HTTPXMock) -> None:
    expected_headers = {"Accept": "text/event-stream", "Last-Event-ID": "41", "cache-control": "no-cache"}
    expected_body = {"subscribed": True}
    httpx2_mock.add_response(
        method="POST",
        url="https://example.com/events?topic=build",
        match_headers=expected_headers,
        match_json=expected_body,
        headers=EVENT_STREAM,
        content=b"event: build\nid: 42\ndata: ready\n\n",
    )


def _mock_open_stream(httpx2_mock: HTTPXMock) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"data: first\n\n"
        pytest.fail("The client read past the first event")

    expected_headers = {"Accept": "text/event-stream", "Cache-Control": "no-store"}
    httpx2_mock.add_response(
        method="GET",
        match_headers=expected_headers,
        headers=EVENT_STREAM,
        stream=IteratorStream(chunks()),
    )
