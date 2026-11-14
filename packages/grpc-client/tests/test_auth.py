from uuid import uuid4

import grpc
import pytest
from grpc_client import options
from grpc_client.interceptors import AuthInterceptor

from .assertions import assert_that
from .clients import GRPCbinServiceClient
from .fakes import FakeAsyncAuth, FakeAuth, FakeContinuation, fake_call_details
from .support import code_number

UNAUTHENTICATED_CODE = code_number(grpc.StatusCode.UNAUTHENTICATED)


def test_sends_bearer_token(service_addr: str) -> None:
    """The access token is sent in the authorization header."""
    auth = FakeAuth(prefix="warehouse")

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        response = client.get_headers()

    assert_that(response).received_metadata("authorization", "Bearer warehouse-1")


def test_issues_token_once_for_several_requests(service_addr: str) -> None:
    """A token is issued once for multiple successful requests."""
    auth = FakeAuth()

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        client.get_headers()
        client.get_headers()

    assert_that(auth.issued).is_length(1)


def test_keeps_user_defined_authorization(service_addr: str) -> None:
    """The caller's custom authorization header is preserved."""
    auth = FakeAuth()

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        response = client.get_headers({"authorization": "Bearer my-own-token"})

    assert_that(response).received_metadata("authorization", "Bearer my-own-token")


def test_does_not_issue_token_when_authorization_is_given(service_addr: str) -> None:
    """An explicit authorization header prevents fetching a token from the provider."""
    auth = FakeAuth()

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        client.get_headers({"authorization": "Bearer external-token"})

    assert_that(auth.issued).is_empty()


def test_refreshes_token_after_unauthenticated(service_addr: str) -> None:
    """A new token is issued after an UNAUTHENTICATED response."""
    auth = FakeAuth()

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(auth.issued).is_length(2)


def test_keeps_single_token_when_retry_is_disabled(service_addr: str) -> None:
    """With retries disabled, UNAUTHENTICATED does not refresh the token."""
    auth = FakeAuth()

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth, retry_on_unauthenticated=False),
    ) as client:
        client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(auth.issued).is_length(1)


def test_returns_error_status_after_failed_retry(service_addr: str) -> None:
    """If the retry is rejected again, an error status is returned."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(FakeAuth()),
    ) as client:
        response = client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(response).has_status_code(grpc.StatusCode.UNAUTHENTICATED)


def test_does_not_refresh_token_for_other_errors(service_addr: str) -> None:
    """Errors unrelated to authentication do not refresh the token."""
    auth = FakeAuth()

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="не найдено")

    assert_that(auth.issued).is_length(1)


def test_rejects_async_auth_in_sync_client(service_addr: str) -> None:
    """The synchronous client rejects asynchronous authentication implementations."""
    with pytest.raises(TypeError):
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(FakeAsyncAuth()),
        )


def test_repeats_call_after_unauthenticated() -> None:
    """The request is retried after an UNAUTHENTICATED response."""
    prefix = uuid4().hex
    auth = FakeAuth(prefix=prefix)
    continuation = FakeContinuation(accepted_token=f"{prefix}-2")
    interceptor = AuthInterceptor(auth)

    interceptor.intercept_unary_unary(continuation, fake_call_details(), object())

    assert_that(continuation.calls).is_length(2)


def test_sends_refreshed_token_in_repeated_call() -> None:
    """The retry uses the new token."""
    prefix = uuid4().hex
    auth = FakeAuth(prefix=prefix)
    continuation = FakeContinuation(accepted_token=f"{prefix}-2")
    interceptor = AuthInterceptor(auth)

    interceptor.intercept_unary_unary(continuation, fake_call_details(), object())

    assert_that(continuation.sent_token(1)).is_equal_to(f"{prefix}-2")


def test_sends_original_token_in_first_call() -> None:
    """The first request uses the initially issued token."""
    prefix = uuid4().hex
    auth = FakeAuth(prefix=prefix)
    continuation = FakeContinuation(accepted_token=f"{prefix}-2")
    interceptor = AuthInterceptor(auth)

    interceptor.intercept_unary_unary(continuation, fake_call_details(), object())

    assert_that(continuation.sent_token(0)).is_equal_to(f"{prefix}-1")


def test_passes_rejected_token_to_refresh() -> None:
    """The token provider is told exactly which token the service rejected."""
    prefix = uuid4().hex
    auth = FakeAuth(prefix=prefix)
    interceptor = AuthInterceptor(auth)

    interceptor.intercept_unary_unary(FakeContinuation(accepted_token=f"{prefix}-2"), fake_call_details(), object())

    assert_that(auth.rejected).is_equal_to([f"{prefix}-1"])


def test_gives_up_after_single_repeat() -> None:
    """If the new token is also rejected, there is no third attempt."""
    continuation = FakeContinuation(accepted_token=None)
    interceptor = AuthInterceptor(FakeAuth())

    interceptor.intercept_unary_unary(continuation, fake_call_details(), object())

    assert_that(continuation.calls).is_length(2)


def test_returns_successful_outcome_of_repeated_call() -> None:
    """The retry response becomes the result."""
    prefix = uuid4().hex
    continuation = FakeContinuation(accepted_token=f"{prefix}-2")
    interceptor = AuthInterceptor(FakeAuth(prefix=prefix))

    outcome = interceptor.intercept_unary_unary(continuation, fake_call_details(), object())

    assert_that(outcome.code()).is_equal_to(grpc.StatusCode.OK)


def test_makes_single_call_when_retry_disabled() -> None:
    """With retries disabled, the request is sent once."""
    continuation = FakeContinuation(accepted_token=None)
    interceptor = AuthInterceptor(FakeAuth(), retry_on_unauthenticated=False)

    interceptor.intercept_unary_unary(continuation, fake_call_details(), object())

    assert_that(continuation.calls).is_length(1)


def test_does_not_repeat_call_with_user_defined_authorization() -> None:
    """A custom authorization header prevents retries."""
    continuation = FakeContinuation(accepted_token=None)
    interceptor = AuthInterceptor(FakeAuth())
    details = fake_call_details(metadata=(("authorization", "Bearer external"),))

    interceptor.intercept_unary_unary(continuation, details, object())

    assert_that(continuation.calls).is_length(1)


def test_keeps_metadata_untouched_with_user_defined_authorization() -> None:
    """Metadata with a custom authorization header is preserved."""
    continuation = FakeContinuation(accepted_token=None)
    interceptor = AuthInterceptor(FakeAuth())
    details = fake_call_details(metadata=(("authorization", "Bearer untouched"),))

    interceptor.intercept_unary_unary(continuation, details, object())

    assert_that(continuation.sent_token(0)).is_equal_to("untouched")
