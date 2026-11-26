"""Both retry options share one loop and attempt budget."""

from typing import cast

import httpx2
import pytest
from http_client import AsyncHttpClient, HttpClient
from http_client_retries.config import RetryOverrides
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from pytest_httpx2 import HTTPXMock
from tenacity import RetryError, stop_after_attempt, stop_after_delay, stop_all

from tests.assertions import assert_that
from tests.conftest import MAX_ATTEMPTS
from tests.fakes import RecordingHook


def is_server_error(response: httpx2.Response) -> bool:
    return response.status_code >= httpx2.codes.INTERNAL_SERVER_ERROR


def alternating_failures(httpx2_mock: HTTPXMock) -> None:
    """Two network errors, then a 503, repeating for any number of attempts."""
    served = {"count": 0}

    def respond(_request: httpx2.Request) -> httpx2.Response:
        served["count"] += 1
        if served["count"] % 3 == 0:
            return httpx2.Response(503)

        message = "link flapping"
        raise httpx2.ConnectError(message)

    httpx2_mock.add_callback(respond, is_reusable=True)


@pytest.mark.usefixtures("fast_retries")
def test_combined_options_share_single_attempt_budget(httpx2_mock: HTTPXMock) -> None:
    alternating_failures(httpx2_mock)

    with (
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(),
            with_retries_if(is_server_error),
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx2.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx2_mock).made_attempts(MAX_ATTEMPTS)


@pytest.mark.usefixtures("fast_retries")
def test_reversed_option_order_keeps_same_budget(httpx2_mock: HTTPXMock) -> None:
    alternating_failures(httpx2_mock)

    with (
        HttpClient(
            "https://gateway.internal",
            with_retries_if(is_server_error),
            with_retries_failed_requests(),
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx2.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx2_mock).made_attempts(MAX_ATTEMPTS)


@pytest.mark.usefixtures("fast_retries")
async def test_combined_options_serve_plain_response_on_async_client(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=200, json=dict[str, object]({"routed": True}))

    async with AsyncHttpClient(
        "https://gateway.internal",
        with_retries_failed_requests(),
        with_retries_if(is_server_error),
    ) as client:
        response = await client.send(httpx2.Request("GET", "https://gateway.internal/route"))

    assert_that(cast("object", response.json())).is_equal_to({"routed": True})


@pytest.mark.usefixtures("fast_retries")
async def test_combined_options_retry_mixed_failures_on_async_client(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("link flapping"))
    httpx2_mock.add_response(status_code=503)
    httpx2_mock.add_response(status_code=200)

    async with AsyncHttpClient(
        "https://gateway.internal",
        with_retries_failed_requests(),
        with_retries_if(is_server_error),
    ) as client:
        await client.send(httpx2.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx2_mock).made_attempts(3)


@pytest.mark.usefixtures("fast_retries")
async def test_combined_options_keep_async_client_usable(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_response(status_code=200, json=dict[str, object]({"ok": True}))

    async with AsyncHttpClient(
        "https://gateway.internal",
        with_retries_if(is_server_error),
        with_retries_failed_requests(),
    ) as client:
        response = await client.send(httpx2.Request("GET", "https://gateway.internal/route"))

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
def test_parameter_declared_in_single_option_applies_to_whole_policy(httpx2_mock: HTTPXMock) -> None:
    httpx2_mock.add_exception(httpx2.ConnectError("link flapping"), is_reusable=True)

    with (
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2))),
            with_retries_if(is_server_error),
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx2.Request("GET", "https://gateway.internal/route"))

    assert_that(httpx2_mock).made_attempts(2)


def test_same_object_declared_in_both_options_is_rejected() -> None:
    limit = stop_after_attempt(2)

    with pytest.raises(ValueError, match="stop"):
        HttpClient(
            "https://gateway.internal",
            with_retries_failed_requests(overrides=RetryOverrides(stop=limit)),
            with_retries_if(is_server_error, overrides=RetryOverrides(stop=limit)),
        )
