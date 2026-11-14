from collections.abc import Iterator

import httpx
from assertpy import assert_that
from http_client.options import with_auth
from httpx import BasicAuth
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory
from .support.streams import assert_chunks

CHUNK_SIZE = 100


def test_stream_request_reads_whole_content(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Read a streaming response in full."""
    payload = b"test content for streaming"
    httpx_mock.add_response(url="https://example.com/stream", method="GET", content=payload)
    client = new_client("https://example.com")

    with client.stream_request(httpx.Request("GET", "https://example.com/stream")) as response:
        content = response.read()

    assert_that(content).is_equal_to(payload)


def test_stream_request_keeps_response_headers(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Streaming response headers are available before reading the body."""
    httpx_mock.add_response(
        url="https://example.com/stream",
        method="GET",
        content=b"body",
        headers={"Content-Type": "text/csv"},
    )
    client = new_client("https://example.com")

    with client.stream_request(httpx.Request("GET", "https://example.com/stream")) as response:
        content_type = response.headers["Content-Type"]

    assert_that(content_type).is_equal_to("text/csv")


def test_stream_request_reads_lines(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Read a streaming response line by line."""
    httpx_mock.add_response(url="https://example.com/lines", method="GET", text="line 1\nline 2\nline 3")
    client = new_client("https://example.com")

    with client.stream_request(httpx.Request("GET", "https://example.com/lines")) as response:
        lines = [line for line in response.iter_lines() if line]

    assert_that(lines).is_equal_to(["line 1", "line 2", "line 3"])


def test_stream_request_respects_requested_chunk_size(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Stream chunks do not exceed the requested size."""
    httpx_mock.add_response(url="https://example.com/chunks", method="GET", content=b"0123456789" * 100)
    client = new_client("https://example.com")

    with client.stream_request(httpx.Request("GET", "https://example.com/chunks")) as response:
        chunks = list(response.iter_bytes(chunk_size=CHUNK_SIZE))

    assert_chunks(chunks).are_no_longer_than(CHUNK_SIZE)


def test_stream_request_splits_large_content(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Content longer than the chunk size arrives in multiple chunks."""
    httpx_mock.add_response(url="https://example.com/chunks", method="GET", content=b"0123456789" * 100)
    client = new_client("https://example.com")

    with client.stream_request(httpx.Request("GET", "https://example.com/chunks")) as response:
        chunks = list(response.iter_bytes(chunk_size=CHUNK_SIZE))

    assert_chunks(chunks).are_split_in_more_than_one()


def test_stream_request_chunks_join_into_content(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Chunks reconstruct the original contents."""
    payload = b"0123456789" * 100
    httpx_mock.add_response(url="https://example.com/chunks", method="GET", content=payload)
    client = new_client("https://example.com")

    with client.stream_request(httpx.Request("GET", "https://example.com/chunks")) as response:
        chunks = list(response.iter_bytes(chunk_size=CHUNK_SIZE))

    assert_chunks(chunks).join_to(payload)


def test_stream_request_sends_prepared_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """stream_request sends the supplied Request without rebuilding it.

    Regression: rebuilding with client.stream() raised RequestNotRead for streaming request bodies.
    """
    httpx_mock.add_response(url="https://example.com/upload", method="POST", content=b"ok")
    client = new_client("https://example.com")

    def chunks() -> Iterator[bytes]:
        yield b"part1"
        yield b"part2"

    with client.stream_request(client.client.build_request("POST", "/upload", content=chunks())) as response:
        response.read()

    assert_that(httpx_mock.get_requests()[0].read()).is_equal_to(b"part1part2")


def test_stream_request_applies_auth_from_call(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Authentication supplied to stream_request is included in the request."""
    httpx_mock.add_response(url="https://example.com/secure", method="GET", content=b"secure data")
    client = new_client("https://example.com")

    with client.stream_request(
        httpx.Request("GET", "https://example.com/secure"),
        auth=BasicAuth(username="reader", password="letmein"),  # noqa: S106
    ) as response:
        response.read()

    assert_that(httpx_mock.get_requests()[0].headers).contains_key("authorization")


def test_stream_request_anonymous_drops_client_auth(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """anonymous=True disables client authentication for streaming requests too."""
    httpx_mock.add_response(url="https://example.com/public", method="GET", content=b"public data")
    client = new_client("https://example.com", with_auth(BasicAuth(username="reader", password="letmein")))  # noqa: S106

    with client.stream_request(httpx.Request("GET", "https://example.com/public"), anonymous=True) as response:
        response.read()

    assert_that(httpx_mock.get_requests()[0].headers).does_not_contain_key("authorization")


def test_send_leaves_stream_unconsumed(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """send(stream=True) yields a response with an unread body."""
    httpx_mock.add_response(url="https://example.com/api/data", method="GET", content=b"x" * 64)
    client = new_client("https://example.com")

    response = client.send(client.client.build_request("GET", "/api/data"), stream=True)
    consumed = response.is_stream_consumed
    response.close()

    assert_that(consumed).is_false()


def test_stream_reads_content_by_method_and_url(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """stream(method, url) follows the httpx contract and yields content."""
    payload = b"httpx-style streaming"
    httpx_mock.add_response(url="https://example.com/data", method="GET", content=payload)
    client = new_client("https://example.com")

    with client.stream("GET", "/data") as response:
        content = response.read()

    assert_that(content).is_equal_to(payload)


def test_stream_sends_given_method(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """stream(method, url) sends a request with the supplied method."""
    httpx_mock.add_response(url="https://example.com/search", method="POST", content=b"result")
    client = new_client("https://example.com")

    with client.stream("POST", "/search", json={"query": "test"}) as response:
        response.read()

    assert_that(httpx_mock.get_requests()[0].method).is_equal_to("POST")


async def test_async_stream_request_reads_whole_content(
    httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    """Read an asynchronous client streaming response in full."""
    payload = b"async test content"
    httpx_mock.add_response(url="https://example.com/async-stream", method="GET", content=payload)
    client = new_async_client("https://example.com")

    async with client.stream_request(httpx.Request("GET", "https://example.com/async-stream")) as response:
        content = await response.aread()

    assert_that(content).is_equal_to(payload)


async def test_async_stream_request_reads_lines(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Read an asynchronous client streaming response line by line."""
    httpx_mock.add_response(url="https://example.com/async-lines", method="GET", text="alpha\nbeta\ngamma")
    client = new_async_client("https://example.com")

    async with client.stream_request(httpx.Request("GET", "https://example.com/async-lines")) as response:
        lines = [line async for line in response.aiter_lines() if line]

    assert_that(lines).is_equal_to(["alpha", "beta", "gamma"])


async def test_async_stream_request_respects_requested_chunk_size(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Asynchronous client stream chunks do not exceed the requested size."""
    httpx_mock.add_response(url="https://example.com/async-chunks", method="GET", content=b"0123456789" * 100)
    client = new_async_client("https://example.com")

    async with client.stream_request(httpx.Request("GET", "https://example.com/async-chunks")) as response:
        chunks = [chunk async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE)]

    assert_chunks(chunks).are_no_longer_than(CHUNK_SIZE)


async def test_async_stream_request_chunks_join_into_content(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Asynchronous stream chunks reconstruct the original contents."""
    payload = b"0123456789" * 100
    httpx_mock.add_response(url="https://example.com/async-chunks", method="GET", content=payload)
    client = new_async_client("https://example.com")

    async with client.stream_request(httpx.Request("GET", "https://example.com/async-chunks")) as response:
        chunks = [chunk async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE)]

    assert_chunks(chunks).join_to(payload)


async def test_async_stream_request_applies_auth_from_call(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Authentication supplied to asynchronous stream_request is included in the request."""
    httpx_mock.add_response(url="https://example.com/secure", method="GET", content=b"secure async data")
    client = new_async_client("https://example.com")

    async with client.stream_request(
        httpx.Request("GET", "https://example.com/secure"),
        auth=BasicAuth(username="worker", password="s3cret"),  # noqa: S106
    ) as response:
        await response.aread()

    assert_that(httpx_mock.get_requests()[0].headers).contains_key("authorization")


async def test_async_stream_reads_content_by_method_and_url(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Asynchronous stream(method, url) follows the httpx contract and yields content."""
    payload = b"async httpx-style streaming"
    httpx_mock.add_response(url="https://example.com/data", method="GET", content=payload)
    client = new_async_client("https://example.com")

    async with client.stream("GET", "/data") as response:
        content = await response.aread()

    assert_that(content).is_equal_to(payload)


async def test_async_stream_sends_given_method(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Asynchronous stream(method, url) sends a request with the supplied method."""
    httpx_mock.add_response(url="https://example.com/upload", method="PUT", content=b"uploaded")
    client = new_async_client("https://example.com")

    async with client.stream("PUT", "/upload", content=b"file data") as response:
        await response.aread()

    assert_that(httpx_mock.get_requests()[0].method).is_equal_to("PUT")
