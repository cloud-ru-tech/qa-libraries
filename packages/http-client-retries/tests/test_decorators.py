"""Retry decorator behavior for synchronous functions."""

from typing import Protocol, cast

import httpx
import pytest
from http_client_retries import configure
from http_client_retries.config import Config
from http_client_retries.decorators import retry_if, retry_if_failed
from pytest_cases import parametrize_with_cases
from tenacity import RetryError, stop_after_attempt, wait_none

from tests import cases
from tests.assertions import assert_that
from tests.conftest import MAX_ATTEMPTS
from tests.fakes import (
    AsyncCallableEndpoint,
    CoroutineReturningHook,
    CountingCondition,
    FlakyEndpoint,
    GenericEndpoint,
    RecordingHook,
    RespondingEndpoint,
)


@pytest.mark.usefixtures("fast_retries")
def test_returns_response_once_condition_stops_matching() -> None:
    accepted = httpx.Response(200, content=b'{"delivered": true}')
    endpoint = RespondingEndpoint(accepted)

    result = retry_if(CountingCondition([True, True, False]))(endpoint)()

    assert_that(result).is_equal_to(accepted)


@pytest.mark.usefixtures("fast_retries")
def test_calls_endpoint_once_per_attempt_while_condition_matches() -> None:
    endpoint = RespondingEndpoint(httpx.Response(202))

    retry_if(CountingCondition([True, True, False]))(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(3)


@pytest.mark.usefixtures("fast_retries")
def test_checks_condition_on_every_attempt() -> None:
    condition = CountingCondition([True, False])

    retry_if(condition)(RespondingEndpoint(httpx.Response(418)))()

    assert_that(condition.calls).is_equal_to(2)


def test_calls_hook_between_attempts(recorded_retries: RecordingHook) -> None:
    retry_if(CountingCondition([True, True, False]))(RespondingEndpoint(httpx.Response(503)))()

    assert_that(len(recorded_retries.calls)).is_equal_to(2)


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_TypedDecorator", parametrize_with_cases("error,failures", cases=cases))
@pytest.mark.usefixtures("fast_retries")
def test_recovers_after_retryable_error(error: Exception, failures: int) -> None:
    succeeded = httpx.Response(204)
    endpoint = FlakyEndpoint(*[error] * failures, succeeded)

    result = retry_if_failed(endpoint)()

    assert_that(result).is_equal_to(succeeded)


@cast("_TypedDecorator", parametrize_with_cases("error,failures", cases=cases))
@pytest.mark.usefixtures("fast_retries")
def test_repeats_call_until_retryable_error_stops(error: Exception, failures: int) -> None:
    endpoint = FlakyEndpoint(*[error] * failures, httpx.Response(200))

    retry_if_failed(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(failures + 1)


@pytest.mark.usefixtures("reraising_retries")
def test_reraises_original_error_when_attempts_run_out() -> None:
    refused = httpx.ConnectError("no route to host", request=httpx.Request("GET", "https://vault.internal/keys"))

    with pytest.raises(httpx.ConnectError) as failure:
        retry_if_failed(FlakyEndpoint(refused, refused, refused))()

    assert_that(failure.value).is_same_as(refused)


@pytest.mark.usefixtures("fast_retries")
def test_keeps_original_error_inside_retry_error() -> None:
    unreachable = httpx.ConnectTimeout("handshake stalled", request=httpx.Request("PUT", "https://ledger.test/tx"))

    with pytest.raises(RetryError) as failure:
        retry_if_failed(FlakyEndpoint(unreachable, unreachable, unreachable))()

    assert_that(failure.value).wraps_error(httpx.ConnectTimeout)


@pytest.mark.usefixtures("fast_retries")
def test_stops_after_configured_number_of_attempts() -> None:
    endpoint = FlakyEndpoint(*[httpx.ReadError("stream cut")] * MAX_ATTEMPTS)

    with pytest.raises(RetryError):
        retry_if_failed(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(MAX_ATTEMPTS)


@pytest.mark.usefixtures("fast_retries")
def test_propagates_error_outside_retryable_list() -> None:
    with pytest.raises(httpx.InvalidURL):
        retry_if_failed(FlakyEndpoint(httpx.InvalidURL("host is missing")))()


@pytest.mark.usefixtures("fast_retries")
def test_does_not_repeat_call_for_error_outside_retryable_list() -> None:
    endpoint = FlakyEndpoint(httpx.StreamConsumed())

    with pytest.raises(httpx.StreamConsumed):
        retry_if_failed(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
def test_repeats_transient_network_error() -> None:
    endpoint = FlakyEndpoint(httpx.ConnectError("сброс"), httpx.Response(200))

    retry_if_failed(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(2)


@cast("_TypedDecorator", parametrize_with_cases("error", cases=cases, prefix="deterministic_"))
@pytest.mark.usefixtures("fast_retries")
def test_does_not_repeat_deterministic_network_error(error: Exception) -> None:
    endpoint = FlakyEndpoint(error, httpx.Response(200))

    with pytest.raises(type(error)):
        retry_if_failed(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(1)


@pytest.mark.usefixtures("recorded_async_retries")
def test_rejects_async_hook_on_sync_client() -> None:
    endpoint = FlakyEndpoint(httpx.ConnectError("сброс"), httpx.Response(200))

    with pytest.raises(TypeError, match="асинхронный"):
        retry_if_failed(endpoint)()


@pytest.mark.usefixtures("fast_retries")
async def test_repeats_call_of_async_callable_object() -> None:
    endpoint = AsyncCallableEndpoint(httpx.ConnectError("сброс"), httpx.Response(200))

    await retry_if_failed(endpoint)()

    assert_that(endpoint.attempts).is_equal_to(2)


@pytest.mark.usefixtures("fast_retries")
async def test_returns_response_from_async_callable_object() -> None:
    accepted = httpx.Response(200, content=b"ok")
    endpoint = AsyncCallableEndpoint(httpx.ConnectError("сброс"), accepted)

    result = await retry_if_failed(endpoint)()

    assert_that(result).is_same_as(accepted)


def test_rejects_hook_that_returns_coroutine() -> None:
    hook = CoroutineReturningHook()
    configure(
        options=Config(stop=stop_after_attempt(3), wait=wait_none(), before_sleep_hook=hook),
    )
    endpoint = FlakyEndpoint(httpx.ConnectError("сброс"), httpx.Response(200))

    with pytest.raises(TypeError, match="асинхронный"):
        retry_if_failed(endpoint)()


@pytest.mark.usefixtures("fast_retries")
def test_preserves_keyword_arguments_and_non_http_return_value() -> None:
    endpoint = GenericEndpoint()
    label = "typed-result"

    result = retry_if_failed(endpoint)(httpx.Request("GET", "https://generic.example/items"), label=label)

    assert_that(result).is_equal_to((label, 2))
