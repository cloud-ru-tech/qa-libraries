"""Retry option behavior for synchronous client streaming requests.

Tests use the real HttpClient.stream_request: the connection opens
in __enter__ rather than at call time, so this is required to test retry behavior.
"""

import logging

import httpx
import pytest
from _pytest.logging import LogCaptureFixture
from http_client import HttpClient
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from pytest_httpx import HTTPXMock
from tenacity import RetryError

from tests.assertions import assert_that


def is_server_error(response: httpx.Response) -> bool:
    return response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR


@pytest.mark.usefixtures("fast_retries")
def test_returns_stream_body_once_connection_recovers(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_response(status_code=200, content=b"quarterly-report-bytes")

    with (
        HttpClient("https://exports.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx.Request("GET", "https://exports.internal/report")) as response,
    ):
        body = response.read()

    assert_that(body).is_equal_to(b"quarterly-report-bytes")


@pytest.mark.usefixtures("fast_retries")
def test_reopens_stream_until_connection_recovers(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_response(status_code=200, content=b"payload")

    with (
        HttpClient("https://exports.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx.Request("GET", "https://exports.internal/report")) as response,
    ):
        response.read()

    assert_that(httpx_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
def test_reopens_stream_opened_through_shortcut(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_response(status_code=200, content=b"backup")

    with (
        HttpClient("https://backups.test", with_retries_failed_requests()) as client,
        client.stream("GET", "/archive") as response,
    ):
        response.read()

    assert_that(httpx_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_retries_every_attempt_against_same_path(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_response(status_code=200, content=b"backup")

    with (
        HttpClient("https://backups.test", with_retries_failed_requests()) as client,
        client.stream("GET", "/archive") as response,
    ):
        response.read()

    assert_that(httpx_mock).requested_path("/archive")


@pytest.mark.usefixtures("fast_retries")
def test_reads_reopened_stream_in_chunks(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("socket closed"))
    httpx_mock.add_response(status_code=200, content=b"alphabravocharlie")

    with (
        HttpClient("https://feeds.example", with_retries_failed_requests()) as client,
        client.stream_request(httpx.Request("GET", "https://feeds.example/live")) as response,
    ):
        chunks = list(response.iter_bytes(chunk_size=5))

    assert_that(chunks).is_equal_to([b"alpha", b"bravo", b"charl", b"ie"])


@pytest.mark.usefixtures("fast_retries")
def test_returns_stream_body_once_condition_stops_matching(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, content=b"ledger-dump")

    with (
        HttpClient("https://ledger.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx.Request("GET", "https://ledger.test/dump")) as response,
    ):
        body = response.read()

    assert_that(body).is_equal_to(b"ledger-dump")


@pytest.mark.usefixtures("fast_retries")
def test_reopens_stream_while_condition_matches(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, content=b"ok")

    with (
        HttpClient("https://ledger.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx.Request("GET", "https://ledger.test/dump")) as response,
    ):
        response.read()

    assert_that(httpx_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_keeps_original_error_when_stream_never_opens(httpx_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx_mock.add_exception(httpx.ConnectError("host unreachable"))

    with (
        HttpClient("https://archive.internal", with_retries_failed_requests()) as client,
        pytest.raises(RetryError) as failure,
        client.stream_request(httpx.Request("GET", "https://archive.internal/blob")),
    ):
        pass

    assert_that(failure.value).wraps_error(httpx.ConnectError)


@pytest.mark.usefixtures("fast_retries")
def test_keeps_last_response_when_stream_condition_never_stops_matching(httpx_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx_mock.add_response(status_code=503)

    with (
        HttpClient("https://ledger.test", with_retries_if(is_server_error)) as client,
        pytest.raises(RetryError) as failure,
        client.stream_request(httpx.Request("GET", "https://ledger.test/dump")),
    ):
        pass

    assert_that(failure.value).returned_response()


@pytest.mark.usefixtures("fast_retries")
def test_opens_stream_once_without_retry_options(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("host unreachable"))

    with (
        HttpClient("https://archive.internal") as client,
        pytest.raises(httpx.ConnectError),
        client.stream_request(httpx.Request("GET", "https://archive.internal/blob")),
    ):
        pass

    assert_that(httpx_mock).made_attempts(1)


def test_logs_failing_stream_before_each_retry(
    httpx_mock: HTTPXMock,
    logging_retries: logging.Logger,
    caplog: LogCaptureFixture,
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("stream aborted"))
    httpx_mock.add_response(status_code=200, content=b"ok")

    with (
        caplog.at_level(logging.ERROR, logger=logging_retries.name),
        HttpClient("https://telemetry.test", with_retries_failed_requests()) as client,
        client.stream_request(httpx.Request("GET", "https://telemetry.test/events")) as response,
    ):
        response.read()

    assert_that(caplog.records).logged_retry_of("GET", "https://telemetry.test/events")
