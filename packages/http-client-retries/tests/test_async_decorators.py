"""Поведение декораторов повторных попыток для асинхронных функций."""

from typing import Protocol, cast

import httpx
import pytest
from http_client_retries.decorators import retry_if, retry_if_failed
from pytest_cases import parametrize_with_cases
from tenacity import RetryError

from tests import cases
from tests.assertions import assert_that
from tests.conftest import MAX_ATTEMPTS
from tests.fakes import CountingCondition, FlakyEndpoint, RecordingAsyncHook, RecordingHook, RespondingEndpoint


@pytest.mark.usefixtures("fast_retries")
async def test_returns_response_once_condition_stops_matching() -> None:
    accepted = httpx.Response(201, content=b'{"created": true}')
    endpoint = RespondingEndpoint(accepted)

    result = await retry_if(CountingCondition([True, True, False]))(endpoint.call_async)()

    assert_that(result).is_equal_to(accepted)


@pytest.mark.usefixtures("fast_retries")
async def test_calls_endpoint_once_per_attempt_while_condition_matches() -> None:
    endpoint = RespondingEndpoint(httpx.Response(429))

    await retry_if(CountingCondition([True, True, False]))(endpoint.call_async)()

    assert_that(endpoint.attempts).is_equal_to(3)


async def test_calls_sync_hook_between_attempts(recorded_retries: RecordingHook) -> None:
    await retry_if(CountingCondition([True, True, False]))(RespondingEndpoint(httpx.Response(502)).call_async)()

    assert_that(len(recorded_retries.calls)).is_equal_to(2)


async def test_awaits_async_hook_between_attempts(recorded_async_retries: RecordingAsyncHook) -> None:
    await retry_if(CountingCondition([True, False]))(RespondingEndpoint(httpx.Response(504)).call_async)()

    assert_that(len(recorded_async_retries.calls)).is_equal_to(1)


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_TypedDecorator", parametrize_with_cases("error,failures", cases=cases))
@pytest.mark.usefixtures("fast_retries")
async def test_recovers_after_retryable_error(error: Exception, failures: int) -> None:
    succeeded = httpx.Response(200, content=b"recovered")
    endpoint = FlakyEndpoint(*[error] * failures, succeeded)

    result = await retry_if_failed(endpoint.call_async)()

    assert_that(result).is_equal_to(succeeded)


@cast("_TypedDecorator", parametrize_with_cases("error,failures", cases=cases))
@pytest.mark.usefixtures("fast_retries")
async def test_repeats_call_until_retryable_error_stops(error: Exception, failures: int) -> None:
    endpoint = FlakyEndpoint(*[error] * failures, httpx.Response(200))

    await retry_if_failed(endpoint.call_async)()

    assert_that(endpoint.attempts).is_equal_to(failures + 1)


@pytest.mark.usefixtures("reraising_retries")
async def test_reraises_original_error_when_attempts_run_out() -> None:
    dropped = httpx.ReadError("peer reset", request=httpx.Request("POST", "https://billing.internal/charges"))

    with pytest.raises(httpx.ReadError) as failure:
        await retry_if_failed(FlakyEndpoint(dropped, dropped, dropped).call_async)()

    assert_that(failure.value).is_same_as(dropped)


@pytest.mark.usefixtures("fast_retries")
async def test_keeps_original_error_inside_retry_error() -> None:
    stalled = httpx.PoolTimeout("no free connection")

    with pytest.raises(RetryError) as failure:
        await retry_if_failed(FlakyEndpoint(stalled, stalled, stalled).call_async)()

    assert_that(failure.value).wraps_error(httpx.PoolTimeout)


@pytest.mark.usefixtures("fast_retries")
async def test_stops_after_configured_number_of_attempts() -> None:
    endpoint = FlakyEndpoint(*[httpx.WriteError("broken pipe")] * MAX_ATTEMPTS)

    with pytest.raises(RetryError):
        await retry_if_failed(endpoint.call_async)()

    assert_that(endpoint.attempts).is_equal_to(MAX_ATTEMPTS)


@pytest.mark.usefixtures("fast_retries")
async def test_does_not_repeat_call_for_error_outside_retryable_list() -> None:
    endpoint = FlakyEndpoint(httpx.InvalidURL("scheme is not supported"))

    with pytest.raises(httpx.InvalidURL):
        await retry_if_failed(endpoint.call_async)()

    assert_that(endpoint.attempts).is_equal_to(1)
