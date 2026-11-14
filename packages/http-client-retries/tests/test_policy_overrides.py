"""Configure retry policies separately for each client."""

from dataclasses import FrozenInstanceError

import httpx
import pytest
from http_client import HttpClient
from http_client_retries import configure, get_config
from http_client_retries.config import Config, RetryOverrides
from http_client_retries.options import with_retries_failed_requests
from pytest_httpx import HTTPXMock
from tenacity import RetryError, stop_after_attempt, wait_none

from tests.assertions import assert_that
from tests.fakes import RecordingHook


@pytest.mark.usefixtures("fast_retries")
def test_client_override_limits_attempts(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)

    with (
        HttpClient(
            "https://cache.internal", with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2)))
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx.Request("GET", "https://cache.internal/key"))

    assert_that(httpx_mock).made_attempts(2)


@pytest.mark.usefixtures("fast_retries")
def test_client_without_override_follows_global_policy(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)

    with HttpClient("https://cache.internal", with_retries_failed_requests()) as client, pytest.raises(RetryError):
        client.send(httpx.Request("GET", "https://cache.internal/key"))

    assert_that(httpx_mock).made_attempts(3)


def test_untouched_setting_follows_global_policy_changed_after_construction(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)
    client = HttpClient(
        "https://sessions.test", with_retries_failed_requests(overrides=RetryOverrides(wait=wait_none()))
    )
    configure(
        options=Config(stop=stop_after_attempt(4), wait=wait_none()),
    )

    with client, pytest.raises(RetryError):
        client.send(httpx.Request("GET", "https://sessions.test/token"))

    assert_that(httpx_mock).made_attempts(4)


@pytest.mark.usefixtures("fast_retries")
def test_client_override_reraises_original_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)

    with (
        HttpClient(
            "https://queue.example", with_retries_failed_requests(overrides=RetryOverrides(reraise=True))
        ) as client,
        pytest.raises(httpx.ConnectError),
    ):
        client.send(httpx.Request("GET", "https://queue.example/job"))


@pytest.mark.usefixtures("fast_retries")
def test_separate_clients_keep_separate_policies(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)

    with (
        HttpClient(
            "https://strict.test", with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2)))
        ) as strict,
        pytest.raises(RetryError),
    ):
        strict.send(httpx.Request("GET", "https://strict.test/ping"))

    attempts_by_strict_client = len(httpx_mock.get_requests())

    with (
        HttpClient(
            "https://patient.test", with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(5)))
        ) as patient,
        pytest.raises(RetryError),
    ):
        patient.send(httpx.Request("GET", "https://patient.test/ping"))

    assert_that(len(httpx_mock.get_requests()) - attempts_by_strict_client).is_equal_to(5)


@pytest.mark.usefixtures("fast_retries")
def test_client_can_switch_off_global_hook(httpx_mock: HTTPXMock) -> None:
    hook = RecordingHook()
    configure(
        options=Config(stop=stop_after_attempt(2), wait=wait_none(), before_sleep_hook=hook),
    )
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)

    with (
        HttpClient(
            "https://quiet.test", with_retries_failed_requests(overrides=RetryOverrides(before_sleep_hook=None))
        ) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx.Request("GET", "https://quiet.test/ping"))

    assert_that(hook.calls).is_empty()


@pytest.mark.usefixtures("fast_retries")
def test_client_without_hook_override_keeps_global_hook(httpx_mock: HTTPXMock) -> None:
    hook = RecordingHook()
    configure(
        options=Config(stop=stop_after_attempt(2), wait=wait_none(), before_sleep_hook=hook),
    )
    httpx_mock.add_exception(httpx.ConnectError("link down"), is_reusable=True)

    with (
        HttpClient("https://noisy.test", with_retries_failed_requests()) as client,
        pytest.raises(RetryError),
    ):
        client.send(httpx.Request("GET", "https://noisy.test/ping"))

    assert_that(hook.calls).is_length(1)


def test_global_configuration_is_replaced_as_a_whole() -> None:
    configure(
        options=Config(stop=stop_after_attempt(7), wait=wait_none()),
    )
    before = get_config()
    configure(
        options=Config(stop=stop_after_attempt(2), wait=wait_none()),
    )

    assert_that(before.stop).is_not_same_as(get_config().stop)


def test_configuration_snapshot_cannot_be_mutated() -> None:
    snapshot = get_config()

    with pytest.raises(FrozenInstanceError):
        setattr(snapshot, "reraise", True)  # noqa: B010 - The type checker would reject direct assignment
