"""Retry option behavior for asynchronous client streaming requests.

As in the synchronous version, tests use the real AsyncHttpClient.stream_request:
the connection opens in __aenter__, so this is required to test retry behavior.
"""

import logging

import httpx2
import pytest
from _pytest.logging import LogCaptureFixture
from http_client import AsyncHttpClient
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from pytest_httpx2 import HTTPXMock
from tenacity import RetryError

from tests.assertions import assert_that


def is_server_error(response: httpx2.Response) -> bool:
    return response.status_code >= httpx2.codes.INTERNAL_SERVER_ERROR


@pytest.mark.usefixtures("fast_retries")
async def test_returns_stream_body_once_connection_recovers(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"nightly-batch")

    async with (
        AsyncHttpClient("https://etl.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://etl.internal/batch")) as response,
    ):
        body = await response.aread()

    assert_that(body).is_equal_to(b"nightly-batch")


@pytest.mark.usefixtures("fast_retries")
async def test_reopens_stream_until_connection_recovers(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"payload")

    async with (
        AsyncHttpClient("https://etl.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://etl.internal/batch")) as response,
    ):
        await response.aread()

    assert_that(httpx2_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
async def test_reopens_stream_opened_through_shortcut(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"snapshot")

    async with (
        AsyncHttpClient("https://snapshots.test", with_retries_failed_requests()) as client,
        client.stream("GET", "/latest") as response,
    ):
        await response.aread()

    assert_that(httpx2_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
async def test_receives_event_after_sse_service_recovers(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=503)
    httpx2_mock.add_response(headers={"Content-Type": "text/event-stream"}, content=b"data: build complete\n\n")

    async with (
        AsyncHttpClient("https://builds.test", with_retries_if(is_server_error)) as client,
        client.sse("/events") as source,
    ):
        event = await anext(aiter(source))

    assert_that(event.data).is_equal_to("build complete")


@pytest.mark.usefixtures("fast_retries")
async def test_reads_reopened_stream_in_chunks(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"deltaechofoxtrot")

    async with (
        AsyncHttpClient("https://feeds.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://feeds.internal/live")) as response,
    ):
        chunks = [chunk async for chunk in response.aiter_bytes(chunk_size=5)]

    assert_that(chunks).is_equal_to([b"delta", b"echof", b"oxtro", b"t"])


@pytest.mark.usefixtures("fast_retries")
async def test_returns_stream_body_once_condition_stops_matching(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=500)
    httpx2_mock.add_response(status_code=500)
    httpx2_mock.add_response(status_code=200, content=b"audit-trail")

    async with (
        AsyncHttpClient("https://compliance.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx2.Request("GET", "https://compliance.test/trail")) as response,
    ):
        body = await response.aread()

    assert_that(body).is_equal_to(b"audit-trail")


@pytest.mark.usefixtures("fast_retries")
async def test_reopens_stream_while_condition_matches(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=504)
    httpx2_mock.add_response(status_code=200, content=b"ok")

    async with (
        AsyncHttpClient("https://compliance.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx2.Request("GET", "https://compliance.test/trail")) as response,
    ):
        await response.aread()

    assert_that(httpx2_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
async def test_keeps_original_error_when_stream_never_opens(httpx2_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx2_mock.add_exception(httpx2.ConnectError("no route to host"))

    async with AsyncHttpClient("https://vault.internal", with_retries_failed_requests()) as client:
        with pytest.raises(RetryError) as failure:
            async with client.stream_request(httpx2.Request("GET", "https://vault.internal/secret")):
                pass

    assert_that(failure.value).wraps_error(httpx2.ConnectError)


@pytest.mark.usefixtures("fast_retries")
async def test_opens_stream_once_without_retry_options(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("no route to host"))

    async with AsyncHttpClient("https://vault.internal") as client:
        with pytest.raises(httpx2.ConnectError):
            async with client.stream_request(httpx2.Request("GET", "https://vault.internal/secret")):
                pass

    assert_that(httpx2_mock).made_attempts(1)


async def test_logs_failing_stream_before_each_retry(
    httpx2_mock: HTTPXMock,
    logging_retries: logging.Logger,
    caplog: LogCaptureFixture,
) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("stream aborted"))
    httpx2_mock.add_response(status_code=200, content=b"ok")

    with caplog.at_level(logging.ERROR, logger=logging_retries.name):
        async with (
            AsyncHttpClient("https://metrics.test", with_retries_failed_requests()) as client,
            client.stream_request(httpx2.Request("GET", "https://metrics.test/scrape")) as response,
        ):
            await response.aread()

    assert_that(caplog.records).logged_retry_of("GET", "https://metrics.test/scrape")
