"""Поведение опций повторных попыток на обычных (непотоковых) запросах клиента."""

import logging
from typing import cast

import httpcore
import httpx
import pytest
from _pytest.logging import LogCaptureFixture
from http_client import AsyncHttpClient, HttpClient
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from pytest_httpx import HTTPXMock

from tests.assertions import assert_that


def is_server_error(response: httpx.Response) -> bool:
    return response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR


@pytest.mark.usefixtures("fast_retries")
def test_returns_response_once_connection_recovers(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("dns lookup failed"))
    httpx_mock.add_exception(httpx.ConnectError("dns lookup failed"))
    httpx_mock.add_response(status_code=200, json=dict[str, object]({"warehouse": "riga"}))

    with HttpClient("https://inventory.internal", with_retries_failed_requests()) as client:
        response = client.send(httpx.Request("GET", "https://inventory.internal/stock"))

    assert_that(cast("object", response.json())).is_equal_to({"warehouse": "riga"})


@pytest.mark.usefixtures("fast_retries")
def test_repeats_request_until_connection_recovers(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("dns lookup failed"))
    httpx_mock.add_exception(httpx.ConnectError("dns lookup failed"))
    httpx_mock.add_response(status_code=200)

    with HttpClient("https://inventory.internal", with_retries_failed_requests()) as client:
        client.send(httpx.Request("GET", "https://inventory.internal/stock"))

    assert_that(httpx_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
async def test_repeats_async_request_until_connection_recovers(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_response(status_code=200)

    async with AsyncHttpClient("https://catalog.test", with_retries_failed_requests()) as client:
        await client.send(httpx.Request("GET", "https://catalog.test/items"))

    assert_that(httpx_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
async def test_repeats_async_request_after_pool_timeout(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpcore.PoolTimeout("connection pool exhausted"))
    httpx_mock.add_response(status_code=200)

    async with AsyncHttpClient("https://catalog.test", with_retries_failed_requests()) as client:
        await client.send(httpx.Request("GET", "https://catalog.test/items"))

    assert_that(httpx_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_returns_response_once_condition_stops_matching(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=500, json=dict[str, object]({"error": "upstream down"}))
    httpx_mock.add_response(status_code=500, json=dict[str, object]({"error": "upstream down"}))
    httpx_mock.add_response(status_code=200, json=dict[str, object]({"quote": 42}))

    with HttpClient("https://pricing.example", with_retries_if(is_server_error)) as client:
        response = client.send(httpx.Request("GET", "https://pricing.example/quote"))

    assert_that(cast("object", response.json())).is_equal_to({"quote": 42})


@pytest.mark.usefixtures("fast_retries")
def test_repeats_request_while_condition_matches(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200)

    with HttpClient("https://pricing.example", with_retries_if(is_server_error)) as client:
        client.send(httpx.Request("GET", "https://pricing.example/quote"))

    assert_that(httpx_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
async def test_repeats_async_request_while_condition_matches(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=502)
    httpx_mock.add_response(status_code=200)

    async with AsyncHttpClient("https://reports.internal", with_retries_if(is_server_error)) as client:
        await client.send(httpx.Request("GET", "https://reports.internal/daily"))

    assert_that(httpx_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_combines_condition_and_connection_retries(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("network unreachable"))
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(status_code=200)

    with HttpClient(
        "https://shipping.test",
        with_retries_if(is_server_error),
        with_retries_failed_requests(),
    ) as client:
        client.send(httpx.Request("GET", "https://shipping.test/labels"))

    assert_that(httpx_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
def test_sends_single_request_without_retry_options(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("network unreachable"))

    with HttpClient("https://shipping.test") as client, pytest.raises(httpx.ConnectError):
        client.send(httpx.Request("GET", "https://shipping.test/labels"))

    assert_that(httpx_mock).made_attempts(1)


def test_logs_failing_request_before_each_retry(
    httpx_mock: HTTPXMock,
    logging_retries: logging.Logger,
    caplog: LogCaptureFixture,
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("tls handshake failed"))
    httpx_mock.add_response(status_code=200)

    with (
        caplog.at_level(logging.ERROR, logger=logging_retries.name),
        HttpClient("https://audit.internal", with_retries_failed_requests()) as client,
    ):
        client.send(httpx.Request("GET", "https://audit.internal/events"))

    assert_that(caplog.records).logged_retry_of("GET", "https://audit.internal/events")


def test_logs_reason_of_each_retry(
    httpx_mock: HTTPXMock,
    logging_retries: logging.Logger,
    caplog: LogCaptureFixture,
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("tls handshake failed"))
    httpx_mock.add_response(status_code=200)

    with (
        caplog.at_level(logging.ERROR, logger=logging_retries.name),
        HttpClient("https://audit.internal", with_retries_failed_requests()) as client,
    ):
        client.send(httpx.Request("GET", "https://audit.internal/events"))

    assert_that(caplog.records).logged_error("ConnectError: tls handshake failed")


def test_logs_status_code_when_retrying_by_condition(
    httpx_mock: HTTPXMock,
    logging_retries: logging.Logger,
    caplog: LogCaptureFixture,
) -> None:
    httpx_mock.add_response(status_code=507)
    httpx_mock.add_response(status_code=200)

    with (
        caplog.at_level(logging.ERROR, logger=logging_retries.name),
        HttpClient("https://audit.internal", with_retries_if(is_server_error)) as client,
    ):
        client.send(httpx.Request("GET", "https://audit.internal/events"))

    assert_that(caplog.records).logged_error("status code = 507")
