import asyncio
import threading
from collections.abc import AsyncIterator, Awaitable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import httpx
import pytest
from http_client import options
from http_client_auth import (
    IAM_AsyncAuth,
    IAM_AsyncHttpClient,
    IAM_Auth,
    IAM_HttpClient,
    InMemoryAsyncAuthStore,
    InMemoryAuthStore,
    Token,
)
from http_client_auth.iam_client import PUBLIC_API_AUTHORIZE_ROUTE
from httpx import codes
from pytest_httpx import HTTPXMock

from . import constants
from .assertions import assert_that
from .factories import (
    async_authorized_client,
    authorized_client,
    delay_sent_requests,
    delay_sent_requests_async,
    iam_auth_response,
)

RESOURCES_PATH = "/resources"
CONCURRENT_CALLERS = 8
IAM_DELAY = 0.05


def _mock_issued_token(httpx_mock: HTTPXMock, access_token: str, expires_in: int = 3600) -> None:
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        json=iam_auth_response(access_token, expires_in),
    )


def _mock_resource(httpx_mock: HTTPXMock, status_code: int = codes.OK) -> None:
    httpx_mock.add_response(
        url=f"{constants.API_URL}{RESOURCES_PATH}",
        method="GET",
        status_code=status_code,
        json=dict[str, object]({"result": "success"}),
    )


def test_puts_issued_token_into_request(httpx_mock: HTTPXMock) -> None:
    """Клиент подставляет в запрос токен, выданный сервисом IAM."""
    access_token = uuid4().hex
    _mock_issued_token(httpx_mock, access_token)
    _mock_resource(httpx_mock)

    with authorized_client("inventory-key", "inventory-secret") as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, access_token)


def test_stores_issued_token(httpx_mock: HTTPXMock) -> None:
    """Клиент сохраняет выданный токен в хранилище."""
    key_id = "catalog-key"
    access_token = uuid4().hex
    store = InMemoryAuthStore()
    _mock_issued_token(httpx_mock, access_token)
    _mock_resource(httpx_mock)

    with authorized_client(key_id, "catalog-secret", store) as client:
        client.get(RESOURCES_PATH)

    assert_that(store.get(key_id)).has_access_token(access_token)


def test_skips_iam_when_stored_token_is_valid(httpx_mock: HTTPXMock) -> None:
    """Клиент не ходит в IAM, пока в хранилище лежит действующий токен."""
    key_id = "reports-key"
    store = InMemoryAuthStore()
    store.set(key_id, Token.with_lifetime("reports-access-token", 3600))
    _mock_resource(httpx_mock)

    with authorized_client(key_id, "reports-secret", store) as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 0)


def test_uses_stored_token_in_request(httpx_mock: HTTPXMock) -> None:
    """Клиент подставляет в запрос токен из хранилища."""
    key_id = "audit-key"
    access_token = uuid4().hex
    store = InMemoryAuthStore()
    store.set(key_id, Token.with_lifetime(access_token, 3600))
    _mock_resource(httpx_mock)

    with authorized_client(key_id, "audit-secret", store) as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, access_token)


def test_requests_new_token_when_stored_one_expired(httpx_mock: HTTPXMock) -> None:
    """Клиент запрашивает новый токен, не дожидаясь отказа сервиса, если срок хранимого истек."""
    key_id = "backup-key"
    store = InMemoryAuthStore()
    store.set(key_id, Token("backup-stale-token", datetime.now(UTC) - timedelta(seconds=1)))
    _mock_issued_token(httpx_mock, "backup-fresh-token")
    _mock_resource(httpx_mock)

    with authorized_client(key_id, "backup-secret", store) as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 1)


def test_sends_refreshed_token_after_expiry(httpx_mock: HTTPXMock) -> None:
    """Клиент подставляет в запрос новый токен взамен истекшего."""
    key_id = "quota-key"
    fresh_token = uuid4().hex
    store = InMemoryAuthStore()
    store.set(key_id, Token("quota-stale-token", datetime.now(UTC) - timedelta(seconds=1)))
    _mock_issued_token(httpx_mock, fresh_token)
    _mock_resource(httpx_mock)

    with authorized_client(key_id, "quota-secret", store) as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, fresh_token)


def test_requests_new_token_after_unauthorized(httpx_mock: HTTPXMock) -> None:
    """Клиент запрашивает новый токен, когда сервис ответил 401."""
    _mock_issued_token(httpx_mock, "billing-first-token")
    _mock_issued_token(httpx_mock, "billing-second-token")
    _mock_resource(httpx_mock, codes.UNAUTHORIZED)
    _mock_resource(httpx_mock)

    with authorized_client("billing-key", "billing-secret") as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 2)


def test_repeats_request_with_new_token_after_unauthorized(httpx_mock: HTTPXMock) -> None:
    """Клиент повторяет запрос с новым токеном, когда сервис ответил 401."""
    second_token = uuid4().hex
    _mock_issued_token(httpx_mock, "shipping-first-token")
    _mock_issued_token(httpx_mock, second_token)
    _mock_resource(httpx_mock, codes.UNAUTHORIZED)
    _mock_resource(httpx_mock)

    with authorized_client("shipping-key", "shipping-secret") as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, second_token)


def test_keeps_token_after_forbidden(httpx_mock: HTTPXMock) -> None:
    """Клиент не запрашивает новый токен, когда сервис ответил 403: прав недостаточно, токен ни при чем."""
    _mock_issued_token(httpx_mock, "support-access-token")
    _mock_resource(httpx_mock, codes.FORBIDDEN)

    with authorized_client("support-key", "support-secret") as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 1)


def test_does_not_repeat_request_after_forbidden(httpx_mock: HTTPXMock) -> None:
    """Клиент не повторяет запрос, когда сервис ответил 403."""
    _mock_issued_token(httpx_mock, "readonly-access-token")
    _mock_resource(httpx_mock, codes.FORBIDDEN)

    with authorized_client("readonly-key", "readonly-secret") as client:
        client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(RESOURCES_PATH, 1)


async def test_async_puts_issued_token_into_request(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент подставляет в запрос токен, выданный сервисом IAM."""
    access_token = uuid4().hex
    _mock_issued_token(httpx_mock, access_token)
    _mock_resource(httpx_mock)

    async with async_authorized_client("async-inventory-key", "async-inventory-secret") as client:
        await client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, access_token)


async def test_async_skips_iam_when_stored_token_is_valid(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент не ходит в IAM, пока в хранилище лежит действующий токен."""
    key_id = "async-reports-key"
    store = InMemoryAsyncAuthStore()
    await store.set(key_id, Token.with_lifetime("async-reports-access-token", 3600))
    _mock_resource(httpx_mock)

    async with async_authorized_client(key_id, "async-reports-secret", store) as client:
        await client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 0)


async def test_async_sends_refreshed_token_after_expiry(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент подставляет в запрос новый токен взамен истекшего."""
    key_id = "async-quota-key"
    fresh_token = uuid4().hex
    store = InMemoryAsyncAuthStore()
    await store.set(key_id, Token("async-quota-stale-token", datetime.now(UTC) - timedelta(seconds=1)))
    _mock_issued_token(httpx_mock, fresh_token)
    _mock_resource(httpx_mock)

    async with async_authorized_client(key_id, "async-quota-secret", store) as client:
        await client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, fresh_token)


async def test_async_requests_new_token_after_unauthorized(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент запрашивает новый токен, когда сервис ответил 401."""
    _mock_issued_token(httpx_mock, "async-billing-first-token")
    _mock_issued_token(httpx_mock, "async-billing-second-token")
    _mock_resource(httpx_mock, codes.UNAUTHORIZED)
    _mock_resource(httpx_mock)

    async with async_authorized_client("async-billing-key", "async-billing-secret") as client:
        await client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 2)


async def test_async_keeps_token_after_forbidden(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент не запрашивает новый токен, когда сервис ответил 403."""
    _mock_issued_token(httpx_mock, "async-support-access-token")
    _mock_resource(httpx_mock, codes.FORBIDDEN)

    async with async_authorized_client("async-support-key", "async-support-secret") as client:
        await client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 1)


def test_buffers_streaming_body_before_first_send(httpx_mock: HTTPXMock) -> None:
    """Клиент вычитывает потоковое тело до первой отправки, иначе повтор после 401 отправить будет нечего."""
    _mock_issued_token(httpx_mock, "upload-access-token")

    with IAM_HttpClient(constants.IAM_URL) as iam_client:
        auth = IAM_Auth("upload-key", "upload-secret", iam_client)
        request = httpx.Request("POST", f"{constants.API_URL}/uploads", content=iter([b"chunk-one", b"chunk-two"]))
        next(auth.sync_auth_flow(request))

    assert_that(request.content).is_equal_to(b"chunk-onechunk-two")


async def test_async_buffers_streaming_body_before_first_send(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент вычитывает потоковое тело до первой отправки."""

    async def chunks() -> AsyncIterator[bytes]:
        yield b"async-chunk-one"
        yield b"async-chunk-two"

    _mock_issued_token(httpx_mock, "async-upload-access-token")

    async with IAM_AsyncHttpClient(constants.IAM_URL) as iam_client:
        auth = IAM_AsyncAuth("async-upload-key", "async-upload-secret", iam_client)
        request = httpx.Request("POST", f"{constants.API_URL}/uploads", content=chunks())
        await cast("Awaitable[httpx.Request]", anext(auth.async_auth_flow(request)))

    assert_that(request.content).is_equal_to(b"async-chunk-oneasync-chunk-two")


class _FalseyAuthStore(InMemoryAuthStore):
    """Хранилище, которое в пустом состоянии ложно по __bool__."""

    def __len__(self) -> int:
        return len(self._tokens)


def _unauthorized_for(request: httpx.Request) -> httpx.Response:
    return httpx.Response(codes.UNAUTHORIZED, request=request)


@pytest.mark.usefixtures("httpx_mock")
def test_reuses_token_refreshed_by_another_caller() -> None:
    """После 401 клиент подставляет токен, который успел обновить другой вызывающий."""
    key_id = "concurrent-key"
    store = InMemoryAuthStore()
    store.set(key_id, Token.with_lifetime("concurrent-stale-token", 3600))
    refreshed = Token.with_lifetime("concurrent-refreshed-token", 3600)

    with IAM_HttpClient(constants.IAM_URL) as iam_client:
        auth = IAM_Auth(key_id, "concurrent-secret", iam_client, store)
        request = httpx.Request("GET", f"{constants.API_URL}{RESOURCES_PATH}")
        flow = auth.sync_auth_flow(request)
        next(flow)
        store.set(key_id, refreshed)
        retried = flow.send(_unauthorized_for(request))

    assert_that(retried.headers["Authorization"]).is_equal_to(f"Bearer {refreshed.access_token}")


def test_skips_iam_when_another_caller_refreshed_token(httpx_mock: HTTPXMock) -> None:
    """После 401 клиент не идет в IAM, если токен в хранилище уже обновлен другим вызывающим."""
    key_id = "concurrent-skip-key"
    store = InMemoryAuthStore()
    store.set(key_id, Token.with_lifetime("concurrent-skip-stale-token", 3600))

    with IAM_HttpClient(constants.IAM_URL) as iam_client:
        auth = IAM_Auth(key_id, "concurrent-skip-secret", iam_client, store)
        request = httpx.Request("GET", f"{constants.API_URL}{RESOURCES_PATH}")
        flow = auth.sync_auth_flow(request)
        next(flow)
        store.set(key_id, Token.with_lifetime("concurrent-skip-refreshed-token", 3600))
        flow.send(_unauthorized_for(request))

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 0)


def test_replaces_expired_token_left_by_another_caller(httpx_mock: HTTPXMock) -> None:
    """После 401 клиент идет в IAM, если в хранилище лежит чужой, но уже истекший токен."""
    key_id = "leftover-key"
    fresh_token = uuid4().hex
    store = InMemoryAuthStore()
    store.set(key_id, Token.with_lifetime("leftover-valid-token", 3600))
    _mock_issued_token(httpx_mock, fresh_token)

    with IAM_HttpClient(constants.IAM_URL) as iam_client:
        auth = IAM_Auth(key_id, "leftover-secret", iam_client, store)
        request = httpx.Request("GET", f"{constants.API_URL}{RESOURCES_PATH}")
        flow = auth.sync_auth_flow(request)
        next(flow)
        store.set(key_id, Token("leftover-expired-token", datetime.now(UTC) - timedelta(seconds=1)))
        retried = flow.send(_unauthorized_for(request))

    assert_that(retried.headers["Authorization"]).is_equal_to(f"Bearer {fresh_token}")


def test_keeps_passed_store_that_looks_empty(httpx_mock: HTTPXMock) -> None:
    """Клиент пишет токен в переданное хранилище, даже если пустым оно ложно по __bool__."""
    key_id = "falsey-key"
    access_token = uuid4().hex
    store = _FalseyAuthStore()
    _mock_issued_token(httpx_mock, access_token)
    _mock_resource(httpx_mock)

    with authorized_client(key_id, "falsey-secret", store) as client:
        client.get(RESOURCES_PATH)

    assert_that(store.get(key_id)).has_access_token(access_token)


async def test_async_repeats_request_with_new_token_after_unauthorized(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент повторяет запрос с новым токеном, когда сервис ответил 401."""
    second_token = uuid4().hex
    _mock_issued_token(httpx_mock, "async-shipping-first-token")
    _mock_issued_token(httpx_mock, second_token)
    _mock_resource(httpx_mock, codes.UNAUTHORIZED)
    _mock_resource(httpx_mock)

    async with async_authorized_client("async-shipping-key", "async-shipping-secret") as client:
        await client.get(RESOURCES_PATH)

    assert_that(httpx_mock).sent_bearer_token_to(RESOURCES_PATH, second_token)


async def test_async_stores_issued_token(httpx_mock: HTTPXMock) -> None:
    """Асинхронный клиент сохраняет выданный токен в хранилище."""
    key_id = "async-catalog-key"
    access_token = uuid4().hex
    store = InMemoryAsyncAuthStore()
    _mock_issued_token(httpx_mock, access_token)
    _mock_resource(httpx_mock)

    async with async_authorized_client(key_id, "async-catalog-secret", store) as client:
        await client.get(RESOURCES_PATH)

    assert_that(await store.get(key_id)).has_access_token(access_token)


@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
def test_requests_token_once_for_concurrent_callers(httpx_mock: HTTPXMock) -> None:
    """При одновременном старте нескольких потоков токен запрашивается в IAM один раз."""
    _mock_issued_token(httpx_mock, "parallel-access-token")
    barrier = threading.Barrier(CONCURRENT_CALLERS)

    with IAM_HttpClient(constants.IAM_URL, options.with_send_decorator(delay_sent_requests(IAM_DELAY))) as iam_client:
        auth = IAM_Auth("parallel-key", "parallel-secret", iam_client, InMemoryAuthStore())

        def authorize_one() -> None:
            request = httpx.Request("GET", f"{constants.API_URL}{RESOURCES_PATH}")
            barrier.wait()
            next(auth.sync_auth_flow(request))

        with ThreadPoolExecutor(max_workers=CONCURRENT_CALLERS) as pool:
            for future in [pool.submit(authorize_one) for _ in range(CONCURRENT_CALLERS)]:
                future.result()

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 1)


@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
async def test_async_requests_token_once_for_concurrent_callers(httpx_mock: HTTPXMock) -> None:
    """При одновременном старте нескольких корутин токен запрашивается в IAM один раз."""
    _mock_issued_token(httpx_mock, "async-parallel-access-token")

    async with IAM_AsyncHttpClient(
        constants.IAM_URL, options.with_send_decorator(delay_sent_requests_async(IAM_DELAY))
    ) as iam_client:
        auth = IAM_AsyncAuth("async-parallel-key", "async-parallel-secret", iam_client, InMemoryAsyncAuthStore())

        async def authorize_one() -> None:
            request = httpx.Request("GET", f"{constants.API_URL}{RESOURCES_PATH}")
            await cast("Awaitable[httpx.Request]", anext(auth.async_auth_flow(request)))

        await asyncio.gather(*[authorize_one() for _ in range(CONCURRENT_CALLERS)])

    assert_that(httpx_mock).sent_requests_to(PUBLIC_API_AUTHORIZE_ROUTE, 1)
