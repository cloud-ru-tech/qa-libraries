"""Обе опции повторов работают в одном цикле с общим бюджетом попыток."""

from typing import cast

import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient
from http_client_retries.config import RetryOverrides
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from pytest_httpx import HTTPXMock
from tenacity import RetryError, stop_after_attempt, stop_after_delay, stop_all

from tests.assertions import assert_that
from tests.conftest import MAX_ATTEMPTS
from tests.fakes import RecordingHook


def is_server_error(response: httpx.Response) -> bool:
    return response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR


def alternating_failures(httpx_mock: HTTPXMock) -> None:
    """Две сетевые ошибки, затем 503 — и так по кругу, сколько бы попыток ни случилось."""
    served = {"count": 0}

    def respond(_request: httpx.Request) -> httpx.Response:
        served["count"] += 1
        if served["count"] % 3 == 0:
            return httpx.Response(503)

        message = "link flapping"
        raise httpx.ConnectError(message)

    httpx_mock.add_callback(respond, is_reusable=True)


@pytest.mark.usefixtures("fast_retries")
def test_combined_options_share_single_attempt_budget(httpx_mock: HTTPXMock) -> None:
    alternating_failures(httpx_mock)

    with (
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(),
            with_retries_if(is_server_error),
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx_mock).made_attempts(MAX_ATTEMPTS)


@pytest.mark.usefixtures("fast_retries")
def test_reversed_option_order_keeps_same_budget(httpx_mock: HTTPXMock) -> None:
    alternating_failures(httpx_mock)

    with (
        HttpClient(
            "https://gateway.internal",
            with_retries_if(is_server_error),
            with_retries_failed_requests(),
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx_mock).made_attempts(MAX_ATTEMPTS)


@pytest.mark.usefixtures("fast_retries")
async def test_combined_options_serve_plain_response_on_async_client(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200, json=dict[str, object]({"routed": True}))

    async with AsyncHttpClient(
        "https://gateway.internal",
        with_retries_failed_requests(),
        with_retries_if(is_server_error),
    ) as client:
        response = await client.send(httpx.Request("GET", "https://gateway.internal/route"))

    assert_that(cast("object", response.json())).is_equal_to({"routed": True})


@pytest.mark.usefixtures("fast_retries")
async def test_combined_options_retry_mixed_failures_on_async_client(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link flapping"))
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200)

    async with AsyncHttpClient(
        "https://gateway.internal",
        with_retries_failed_requests(),
        with_retries_if(is_server_error),
    ) as client:
        await client.send(httpx.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
async def test_combined_options_keep_async_client_usable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200, json=dict[str, object]({"ok": True}))

    async with AsyncHttpClient(
        "https://gateway.internal",
        with_retries_if(is_server_error),
        with_retries_failed_requests(),
    ) as client:
        response = await client.send(httpx.Request("GET", "https://gateway.internal/route"))

    assert_that(cast("object", response.json())).is_equal_to({"ok": True})


def test_conflicting_policy_between_options_names_the_parameter() -> None:
    with pytest.raises(ValueError, match="stop"):
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2))),
            with_retries_if(is_server_error, overrides=RetryOverrides(stop=stop_after_attempt(7))),
        )


def test_same_parameter_declared_twice_is_rejected() -> None:
    with pytest.raises(ValueError, match="stop"):
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2))),
            with_retries_if(is_server_error, overrides=RetryOverrides(stop=stop_after_attempt(2))),
        )


def test_composite_strategy_declared_twice_is_rejected() -> None:
    def limit() -> stop_all:
        return stop_all(stop_after_attempt(3), stop_after_delay(10))

    with pytest.raises(ValueError, match="stop"):
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=limit())),
            with_retries_if(is_server_error, overrides=RetryOverrides(stop=limit())),
        )


def test_distinct_hooks_declared_in_both_options_are_rejected() -> None:
    with pytest.raises(ValueError, match="before_sleep_hook"):
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(before_sleep_hook=RecordingHook())),
            with_retries_if(is_server_error, overrides=RetryOverrides(before_sleep_hook=RecordingHook())),
        )


@pytest.mark.usefixtures("fast_retries")
def test_parameter_declared_in_single_option_applies_to_whole_policy(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link flapping"), is_reusable=True)

    with (
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2))),
            with_retries_if(is_server_error),
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx_mock).made_attempts(2)


def test_same_object_declared_in_both_options_is_rejected() -> None:
    limit = stop_after_attempt(2)

    with pytest.raises(ValueError, match="stop"):
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=limit)),
            with_retries_if(is_server_error, overrides=RetryOverrides(stop=limit)),
        )
