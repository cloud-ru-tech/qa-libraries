import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import grpc
from grpc_client import options
from grpc_client_auth import IAM_GrpcAuth, IAM_HttpClient, IAM_OpenID_HttpClient, InMemoryAuthStore, Token
from httpx import codes
from pytest_httpx import HTTPXMock

from .assertions import assert_that
from .clients import GRPCbinServiceClient
from .conftest import IAM_URL, iam_auth_response
from .fakes import ConstantIamClient, SlowIamClient
from .support import code_number

PUBLIC_API_ROUTE = "/api/v1/auth/token"
OPEN_ID_ROUTE = "/auth/system/openid/token"
UNAUTHENTICATED_CODE = 16


def test_sends_token_received_from_iam(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token received from IAM is sent in the authorization header."""
    access_token = uuid4().hex
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response(access_token))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        response = client.get_headers()

    assert_that(response).received_metadata("authorization", f"Bearer {access_token}")


def test_requests_token_from_public_api(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token is requested through the public IAM API."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("public-api-token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        client.get_headers()

    assert_that([request.url.path for request in httpx_mock.get_requests()]).contains(PUBLIC_API_ROUTE)


def test_requests_token_from_openid_api(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The OpenID client requests tokens through the IAM openid API."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("openid-token"))

    with (
        IAM_OpenID_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        client.get_headers()

    assert_that([request.url.path for request in httpx_mock.get_requests()]).contains(OPEN_ID_ROUTE)


def test_requests_token_once_for_several_requests(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """Multiple requests fetch a token from IAM only once."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("cached-token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        client.get_headers()
        client.get_headers()

    assert_that(httpx_mock.get_requests()).is_length(1)


def test_requests_new_token_when_stored_one_expired(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """An expired stored token is replaced by a newly requested one."""
    store = InMemoryAuthStore()
    store.set("key-id", Token("stale-token", datetime.now(UTC) - timedelta(seconds=1)))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("fresh-token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client, store)),
        ) as client,
    ):
        response = client.get_headers()

    assert_that(response).received_metadata("authorization", "Bearer fresh-token")


def test_reuses_token_from_store(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """A valid stored token is used without contacting IAM."""
    store = InMemoryAuthStore()
    store.set("key-id", Token.with_lifetime("stored-token", 3600))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client, store)),
        ) as client,
    ):
        client.get_headers()

    assert_that(httpx_mock.get_requests()).is_empty()


def test_saves_received_token_to_store(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token received from IAM is saved in storage."""
    store = InMemoryAuthStore()
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("token-to-store"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client, store)),
        ) as client,
    ):
        client.get_headers()

    assert_that(store).stores_token("key-id", "token-to-store")


def test_requests_new_token_after_unauthenticated(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token is requested from IAM again after an UNAUTHENTICATED response."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("first-token"))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("second-token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(httpx_mock.get_requests()).is_length(2)


def test_returns_unauthenticated_when_new_token_is_rejected(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """If the service also rejects the new token, an error status is returned."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("first-token"))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("second-token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        response = client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(response).has_status_code(grpc.StatusCode.UNAUTHENTICATED)


def test_keeps_token_for_other_errors(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """Errors unrelated to authentication do not trigger another IAM request."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("stable-token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="не найдено")

    assert_that(httpx_mock.get_requests()).is_length(1)


def test_sends_key_id_to_iam(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The key identifier is sent in the token request."""
    key_id = "delivery-key-id"
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("token"))

    with (
        IAM_HttpClient(IAM_URL) as iam_client,
        GRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAuth(key_id, "key-secret", iam_client)),
        ) as client,
    ):
        client.get_headers()

    assert_that(httpx_mock.get_requests()[0].content.decode()).contains(key_id)


def test_issues_single_token_for_concurrent_refresh() -> None:
    """Threads whose shared token is rejected concurrently make one IAM request.

    Threads are synchronized by a barrier and the IAM client responds with a delay: without a lock
    inside the authentication object, every thread would request its own token.
    """
    iam_client = SlowIamClient()
    auth = IAM_GrpcAuth("key-id", "key-secret", iam_client)
    rejected = auth.token()

    _refresh_concurrently(auth, rejected, threads_count=4)

    assert_that(iam_client.calls).is_equal_to(2)


def test_returns_same_token_to_concurrent_refresh() -> None:
    """All threads refreshing concurrently receive the same token."""
    auth = IAM_GrpcAuth("key-id", "key-secret", SlowIamClient())
    rejected = auth.token()

    tokens = _refresh_concurrently(auth, rejected, threads_count=4)

    assert_that(set(tokens)).is_length(1)


def _refresh_concurrently(auth: IAM_GrpcAuth, rejected_token: str, threads_count: int) -> list[str]:
    """Refresh a token concurrently from multiple threads.

    :param auth: token provider
    :param rejected_token: token rejected by the service
    :param threads_count: number of threads
    :return: tokens received by each thread
    """
    barrier = threading.Barrier(threads_count)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        token = auth.refresh(rejected_token)
        with lock:
            results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return results


def test_issues_new_token_for_repeatedly_rejected_token(httpx_mock: HTTPXMock) -> None:
    """If an already refreshed token is rejected, another token is issued."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("token-one"))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("token-two"))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("token-three"))

    with IAM_HttpClient(IAM_URL) as iam_client:
        auth = IAM_GrpcAuth("key-id", "key-secret", iam_client)
        first = auth.token()
        second = auth.refresh(first)

        assert_that(auth.refresh(second)).is_equal_to("token-three")


def test_issues_single_token_when_iam_repeats_same_value() -> None:
    """A refresh is recognized even when IAM returns the same token text.

    Such a refresh is indistinguishable from the old token text, so the authentication object
    counts generations; otherwise every waiting caller would contact IAM.
    """
    iam_client = ConstantIamClient()
    auth = IAM_GrpcAuth("key-id", "key-secret", iam_client)
    rejected = auth.token()

    _refresh_concurrently(auth, rejected, threads_count=4)

    assert_that(iam_client.calls).is_equal_to(2)
