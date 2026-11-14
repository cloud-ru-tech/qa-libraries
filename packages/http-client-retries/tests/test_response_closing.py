"""A rejected response releases its connection before the next attempt."""

import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient
from http_client_retries.options import with_retries_if
from pytest_httpx import HTTPXMock
from tenacity import RetryError

from tests.assertions import assert_that
from tests.fakes import ClosableAsyncStream, ClosableStream


def is_server_error(response: httpx.Response) -> bool:
    return response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR


@pytest.mark.usefixtures("fast_retries")
def test_closes_every_rejected_response_of_streaming_send(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(503, stream=ClosableStream(ledger)),
        is_reusable=True,
    )

    with HttpClient("https://ingest.test", with_retries_if(is_server_error)) as client, pytest.raises(RetryError):
        client.send(httpx.Request("GET", "https://ingest.test/events"), stream=True)

    assert_that(ledger.get("closed")).is_equal_to(ledger.get("opened"))


@pytest.mark.usefixtures("fast_retries")
async def test_closes_every_rejected_response_of_async_streaming_send(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(503, stream=ClosableAsyncStream(ledger)),
        is_reusable=True,
    )

    async with AsyncHttpClient("https://ingest.test", with_retries_if(is_server_error)) as client:
        with pytest.raises(RetryError):
            await client.send(httpx.Request("GET", "https://ingest.test/events"), stream=True)

    assert_that(ledger.get("closed")).is_equal_to(ledger.get("opened"))


@pytest.mark.usefixtures("fast_retries")
def test_closes_every_rejected_stream_request(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(503, stream=ClosableStream(ledger)),
        is_reusable=True,
    )

    with (
        HttpClient("https://ingest.test", with_retries_if(is_server_error)) as client,
        pytest.raises(RetryError),
        client.stream_request(httpx.Request("GET", "https://ingest.test/events")),
    ):
        pass

    assert_that(ledger.get("closed")).is_equal_to(ledger.get("opened"))


@pytest.mark.usefixtures("fast_retries")
def test_closes_stream_when_condition_raises(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(200, stream=ClosableStream(ledger)),
        is_reusable=True,
    )

    def broken_condition(_response: httpx.Response) -> bool:
        message = "условие не смогло разобрать ответ"
        raise RuntimeError(message)

    with (
        HttpClient("https://ingest.test", with_retries_if(broken_condition)) as client,
        pytest.raises(RuntimeError),
        client.stream_request(httpx.Request("GET", "https://ingest.test/events")),
    ):
        pass

    assert_that(ledger.get("closed")).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
async def test_closes_async_stream_when_condition_raises(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(200, stream=ClosableAsyncStream(ledger)),
        is_reusable=True,
    )

    def broken_condition(_response: httpx.Response) -> bool:
        message = "условие не смогло разобрать ответ"
        raise RuntimeError(message)

    async with AsyncHttpClient("https://ingest.test", with_retries_if(broken_condition)) as client:
        with pytest.raises(RuntimeError):
            async with client.stream_request(httpx.Request("GET", "https://ingest.test/events")):
                pass

    assert_that(ledger.get("closed")).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
def test_keeps_accepted_stream_open_for_reading(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_callback(lambda _request: httpx.Response(200, stream=ClosableStream(ledger, b"final-payload")))

    with (
        HttpClient("https://ingest.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx.Request("GET", "https://ingest.test/events")) as response,
    ):
        body = response.read()

    assert_that(body).is_equal_to(b"final-payload")


@pytest.mark.usefixtures("fast_retries")
def test_closes_streaming_send_when_condition_raises(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(200, stream=ClosableStream(ledger)),
        is_reusable=True,
    )

    def broken_condition(_response: httpx.Response) -> bool:
        message = "условие не смогло разобрать ответ"
        raise RuntimeError(message)

    with HttpClient("https://ingest.test", with_retries_if(broken_condition)) as client, pytest.raises(RuntimeError):
        client.send(httpx.Request("GET", "https://ingest.test/events"), stream=True)

    assert_that(ledger.get("closed")).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
async def test_closes_async_streaming_send_when_condition_raises(httpx_mock: HTTPXMock) -> None:
    ledger: dict[str, int] = {}
    httpx_mock.add_callback(
        lambda _request: httpx.Response(200, stream=ClosableAsyncStream(ledger)),
        is_reusable=True,
    )

    def broken_condition(_response: httpx.Response) -> bool:
        message = "условие не смогло разобрать ответ"
        raise RuntimeError(message)

    async with AsyncHttpClient("https://ingest.test", with_retries_if(broken_condition)) as client:
        with pytest.raises(RuntimeError):
            await client.send(httpx.Request("GET", "https://ingest.test/events"), stream=True)

    assert_that(ledger.get("closed")).is_equal_to(1)
