import asyncio
from uuid import uuid4

import grpc
from grpc_client import options
from grpc_client_auth import (
    IAM_AsyncHttpClient,
    IAM_GrpcAsyncAuth,
    IAM_OpenID_AsyncHttpClient,
    InMemoryAsyncAuthStore,
    Token,
)
from httpx import codes
from pytest_httpx import HTTPXMock

from .assertions import assert_that
from .clients import AsyncGRPCbinServiceClient
from .conftest import IAM_URL, iam_auth_response
from .fakes import ConstantAsyncIamClient, SlowAsyncIamClient

OPEN_ID_ROUTE = "/auth/system/openid/token"
UNAUTHENTICATED_CODE = 16


async def test_sends_token_received_from_iam(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token received from IAM is sent in the authorization header."""
    access_token = uuid4().hex
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response(access_token))

    async with (
        IAM_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        response = await client.get_headers()

    assert_that(response).received_metadata("authorization", f"Bearer {access_token}")


async def test_requests_token_from_openid_api(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The OpenID client requests tokens through the IAM openid API."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-openid-token"))

    async with (
        IAM_OpenID_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        await client.get_headers()

    assert_that([request.url.path for request in httpx_mock.get_requests()]).contains(OPEN_ID_ROUTE)


async def test_requests_token_once_for_several_requests(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """Multiple requests fetch a token from IAM only once."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-cached-token"))

    async with (
        IAM_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        await client.get_headers()
        await client.get_headers()

    assert_that(httpx_mock.get_requests()).is_length(1)


async def test_reuses_token_from_store(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """A valid stored token is used without contacting IAM."""
    store = InMemoryAsyncAuthStore()
    await store.set("key-id", Token.with_lifetime("async-stored-token", 3600))

    async with (
        IAM_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client, store)),
        ) as client,
    ):
        await client.get_headers()

    assert_that(httpx_mock.get_requests()).is_empty()


async def test_requests_new_token_after_unauthenticated(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token is requested from IAM again after an UNAUTHENTICATED response."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-first-token"))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-second-token"))

    async with (
        IAM_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        await client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(httpx_mock.get_requests()).is_length(2)


async def test_returns_unauthenticated_when_new_token_is_rejected(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """If the service also rejects the new token, an error status is returned."""
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-first-token"))
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-second-token"))

    async with (
        IAM_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)),
        ) as client,
    ):
        response = await client.specific_error(code=UNAUTHENTICATED_CODE, reason="токен просрочен")

    assert_that(response).has_status_code(grpc.StatusCode.UNAUTHENTICATED)


async def test_issues_single_token_for_concurrent_refresh() -> None:
    """Coroutines whose shared token is rejected concurrently make a single IAM request."""
    iam_client = SlowAsyncIamClient()
    auth = IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)
    rejected = await auth.token()

    await asyncio.gather(*(auth.refresh(rejected) for _ in range(4)))

    assert_that(iam_client.calls).is_equal_to(2)


async def test_returns_same_token_to_concurrent_refresh() -> None:
    """All coroutines refreshing concurrently receive the same token."""
    auth = IAM_GrpcAsyncAuth("key-id", "key-secret", SlowAsyncIamClient())
    rejected = await auth.token()

    tokens = await asyncio.gather(*(auth.refresh(rejected) for _ in range(4)))

    assert_that(set(tokens)).is_length(1)


async def test_saves_received_token_to_store(service_addr: str, httpx_mock: HTTPXMock) -> None:
    """The token received from IAM is saved in storage."""
    store = InMemoryAsyncAuthStore()
    httpx_mock.add_response(status_code=codes.OK, json=iam_auth_response("async-token-to-store"))

    async with (
        IAM_AsyncHttpClient(IAM_URL) as iam_client,
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client, store)),
        ) as client,
    ):
        await client.get_headers()

    stored = await store.get("key-id")

    assert_that(stored).has_access_token("async-token-to-store")


async def test_issues_single_token_when_iam_repeats_same_value() -> None:
    """A refresh is recognized even when IAM returns the same token text."""
    iam_client = ConstantAsyncIamClient()
    auth = IAM_GrpcAsyncAuth("key-id", "key-secret", iam_client)
    rejected = await auth.token()

    await asyncio.gather(*(auth.refresh(rejected) for _ in range(4)))

    assert_that(iam_client.calls).is_equal_to(2)
