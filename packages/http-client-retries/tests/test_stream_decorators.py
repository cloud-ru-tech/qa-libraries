"""Retry option behavior for synchronous client streaming requests.

Tests use the real HttpClient.stream_request: the connection opens
in __enter__ rather than at call time, so this is required to test retry behavior.
"""

import logging

import httpx2
import pytest
from _pytest.logging import LogCaptureFixture
from http_client import HttpClient
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from pytest_httpx2 import HTTPXMock
from tenacity import RetryError

from tests.assertions import assert_that


def is_server_error(response: httpx2.Response) -> bool:
    return response.status_code >= httpx2.codes.INTERNAL_SERVER_ERROR


@pytest.mark.usefixtures("fast_retries")
def test_returns_stream_body_once_connection_recovers(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"quarterly-report-bytes")

    with (
        HttpClient("https://exports.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://exports.internal/report")) as response,
    ):
        body = response.read()

    assert_that(body).is_equal_to(b"quarterly-report-bytes")


@pytest.mark.usefixtures("fast_retries")
def test_reopens_stream_until_connection_recovers(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"payload")

    with (
        HttpClient("https://exports.internal", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://exports.internal/report")) as response,
    ):
        response.read()

    assert_that(httpx2_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
def test_reopens_stream_opened_through_shortcut(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"backup")

    with (
        HttpClient("https://backups.test", with_retries_failed_requests()) as client,
        client.stream("GET", "/archive") as response,
    ):
        response.read()

    assert_that(httpx2_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_receives_event_after_sse_service_recovers(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=503)
    httpx2_mock.add_response(headers={"Content-Type": "text/event-stream"}, content=b"data: build complete\n\n")

    with (
        HttpClient("https://builds.test", with_retries_if(is_server_error)) as client,
        client.sse("/events") as source,
    ):
        event = next(iter(source))

    assert_that(event.data).is_equal_to("build complete")


@pytest.mark.usefixtures("fast_retries")
def test_retries_every_attempt_against_same_path(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"backup")

    with (
        HttpClient("https://backups.test", with_retries_failed_requests()) as client,
        client.stream("GET", "/archive") as response,
    ):
        response.read()

    assert_that(httpx2_mock).requested_path("/archive")


@pytest.mark.usefixtures("fast_retries")
def test_reads_reopened_stream_in_chunks(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("socket closed"))
    httpx2_mock.add_response(status_code=200, content=b"alphabravocharlie")

    with (
        HttpClient("https://feeds.example", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://feeds.example/live")) as response,
    ):
        chunks = list(response.iter_bytes(chunk_size=5))

    assert_that(chunks).is_equal_to([b"alpha", b"bravo", b"charl", b"ie"])


@pytest.mark.usefixtures("fast_retries")
def test_returns_stream_body_once_condition_stops_matching(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=503)
    httpx2_mock.add_response(status_code=503)
    httpx2_mock.add_response(status_code=200, content=b"ledger-dump")

    with (
        HttpClient("https://ledger.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx2.Request("GET", "https://ledger.test/dump")) as response,
    ):
        body = response.read()

    assert_that(body).is_equal_to(b"ledger-dump")


@pytest.mark.usefixtures("fast_retries")
def test_reopens_stream_while_condition_matches(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=503)
    httpx2_mock.add_response(status_code=200, content=b"ok")

    with (
        HttpClient("https://ledger.test", with_retries_if(is_server_error)) as client,
        client.stream_request(httpx2.Request("GET", "https://ledger.test/dump")) as response,
    ):
        response.read()

    assert_that(httpx2_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_keeps_original_error_when_stream_never_opens(httpx2_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx2_mock.add_exception(httpx2.ConnectError("host unreachable"))

    with (
        HttpClient("https://archive.internal", with_retries_failed_requests()) as client,
        pytest.raises(RetryError) as failure,
        client.stream_request(httpx2.Request("GET", "https://archive.internal/blob")),
    ):
        pass

    assert_that(failure.value).wraps_error(httpx2.ConnectError)


@pytest.mark.usefixtures("fast_retries")
def test_keeps_last_response_when_stream_condition_never_stops_matching(httpx2_mock: HTTPXMock) -> None:
    for _ in range(3):
        httpx2_mock.add_response(status_code=503)

    with (
        HttpClient("https://ledger.test", with_retries_if(is_server_error)) as client,
        pytest.raises(RetryError) as failure,
        client.stream_request(httpx2.Request("GET", "https://ledger.test/dump")),
    ):
        pass

    assert_that(failure.value).returned_response()


@pytest.mark.usefixtures("fast_retries")
def test_opens_stream_once_without_retry_options(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("host unreachable"))

    with (
        HttpClient("https://archive.internal") as client,
        pytest.raises(httpx2.ConnectError),
        client.stream_request(httpx2.Request("GET", "https://archive.internal/blob")),
    ):
        pass

    assert_that(httpx2_mock).made_attempts(1)


def test_logs_failing_stream_before_each_retry(
    httpx2_mock: HTTPXMock,
    logging_retries: logging.Logger,
    caplog: LogCaptureFixture,
) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("stream aborted"))
    httpx2_mock.add_response(status_code=200, content=b"ok")

    with (
        caplog.at_level(logging.ERROR, logger=logging_retries.name),
        HttpClient("https://telemetry.test", with_retries_failed_requests()) as client,
        client.stream_request(httpx2.Request("GET", "https://telemetry.test/events")) as response,
    ):
        response.read()

    assert_that(caplog.records).logged_retry_of("GET", "https://telemetry.test/events")
