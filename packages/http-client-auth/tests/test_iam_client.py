from typing import Protocol, cast
from uuid import uuid4

import pytest
from http_client import options
from http_client_auth import IAM_HttpClient, IAM_OpenID_HttpClient
from http_client_auth.exceptions import IAM_AuthError, IAM_InvalidJsonResponseError
from http_client_auth.iam_client import OPEN_ID_AUTHORIZE_ROUTE, PUBLIC_API_AUTHORIZE_ROUTE
from httpx import codes
from pytest_cases import parametrize_with_cases
from pytest_httpx import HTTPXMock

from . import constants
from .assertions import assert_that
from .factories import AsyncIamCase, SyncIamCase, iam_auth_response, record_sent_requests


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_TypedDecorator", parametrize_with_cases("iam", has_tag="sync"))
def test_sends_credentials_to_iam(httpx_mock: HTTPXMock, iam: SyncIamCase) -> None:
    """Клиент отправляет в IAM идентификатор ключа и секрет."""
    key_id, key_secret = "orders-key", "orders-secret"
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{iam.route}",
        method="POST",
        json=iam_auth_response("token-for-orders"),
    )

    with iam.client_class(constants.IAM_URL) as client:
        client.authorize(key_id, key_secret)

    assert_that(httpx_mock).sent_json_to(iam.route, iam.payload_of(key_id, key_secret))


@cast("_TypedDecorator", parametrize_with_cases("iam", has_tag="sync"))
def test_returns_access_token(httpx_mock: HTTPXMock, iam: SyncIamCase) -> None:
    """Клиент возвращает токен доступа из ответа IAM."""
    access_token = uuid4().hex
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{iam.route}",
        method="POST",
        json=iam_auth_response(access_token),
    )

    with iam.client_class(constants.IAM_URL) as client:
        auth_data = client.authorize("billing-key", "billing-secret")

    assert_that(auth_data.access_token).is_equal_to(access_token)


@cast("_TypedDecorator", parametrize_with_cases("iam", has_tag="sync"))
def test_returns_token_lifetime(httpx_mock: HTTPXMock, iam: SyncIamCase) -> None:
    """Клиент возвращает время жизни токена из ответа IAM."""
    expires_in = 900
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{iam.route}",
        method="POST",
        json=iam_auth_response("short-lived-token", expires_in),
    )

    with iam.client_class(constants.IAM_URL) as client:
        auth_data = client.authorize("metrics-key", "metrics-secret")

    assert_that(auth_data.expires_in).is_equal_to(expires_in)


def test_raises_on_unsuccessful_status(httpx_mock: HTTPXMock) -> None:
    """Клиент сообщает об ошибке авторизации, если IAM ответил не 200."""
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        status_code=codes.UNAUTHORIZED,
        json=dict[str, object]({"message": "invalid credentials"}),
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_AuthError):
        client.authorize("revoked-key", "revoked-secret")


def test_raises_on_malformed_body(httpx_mock: HTTPXMock) -> None:
    """Клиент сообщает об ошибке разбора, если в ответе IAM не JSON."""
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        status_code=codes.OK,
        content=b"<html>gateway timeout</html>",
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_InvalidJsonResponseError):
        client.authorize("proxied-key", "proxied-secret")


def test_raises_when_access_token_is_missing(httpx_mock: HTTPXMock) -> None:
    """Клиент сообщает об ошибке разбора, если в ответе IAM нет токена доступа."""
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        status_code=codes.OK,
        json=dict[str, object]({"expires_in": 3600}),
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_InvalidJsonResponseError):
        client.authorize("partial-key", "partial-secret")


def test_keeps_token_out_of_parse_error_message(httpx_mock: HTTPXMock) -> None:
    """Сообщение об ошибке разбора не содержит токен доступа из тела ответа."""
    leaked_token = uuid4().hex
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        status_code=codes.OK,
        json=dict[str, object]({"access_token": leaked_token}),
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_InvalidJsonResponseError) as error:
        client.authorize("leaky-key", "leaky-secret")

    assert_that(str(error.value)).does_not_contain(leaked_token)


@cast("_TypedDecorator", parametrize_with_cases("iam", has_tag="async"))
async def test_async_sends_credentials_to_iam(httpx_mock: HTTPXMock, iam: AsyncIamCase) -> None:
    """Асинхронный клиент отправляет в IAM идентификатор ключа и секрет."""
    key_id, key_secret = "async-orders-key", "async-orders-secret"
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{iam.route}",
        method="POST",
        json=iam_auth_response("token-for-async-orders"),
    )

    async with iam.client_class(constants.IAM_URL) as client:
        await client.authorize(key_id, key_secret)

    assert_that(httpx_mock).sent_json_to(iam.route, iam.payload_of(key_id, key_secret))


@cast("_TypedDecorator", parametrize_with_cases("iam", has_tag="async"))
async def test_async_returns_access_token(httpx_mock: HTTPXMock, iam: AsyncIamCase) -> None:
    """Асинхронный клиент возвращает токен доступа из ответа IAM."""
    access_token = uuid4().hex
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{iam.route}",
        method="POST",
        json=iam_auth_response(access_token),
    )

    async with iam.client_class(constants.IAM_URL) as client:
        auth_data = await client.authorize("async-billing-key", "async-billing-secret")

    assert_that(auth_data.access_token).is_equal_to(access_token)


def test_accepts_response_without_id_token(httpx_mock: HTTPXMock) -> None:
    """Клиент принимает ответ IAM без поля id_token: OpenID возвращает его не всегда."""
    access_token = uuid4().hex
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{OPEN_ID_AUTHORIZE_ROUTE}",
        method="POST",
        json=dict[str, object]({"access_token": access_token, "expires_in": 3600, "token_type": "Bearer"}),
    )

    with IAM_OpenID_HttpClient(constants.IAM_URL) as client:
        auth_data = client.authorize("openid-key", "openid-secret")

    assert_that(auth_data.access_token).is_equal_to(access_token)


def test_sends_authorize_request_through_send_decorators(httpx_mock: HTTPXMock) -> None:
    """Запрос авторизации проходит через send-декораторы клиента, а не мимо них."""
    calls: list[str] = []
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        json=iam_auth_response("decorated-access-token"),
    )

    with IAM_HttpClient(constants.IAM_URL, options.with_send_decorator(record_sent_requests(calls))) as client:
        client.authorize("decorated-key", "decorated-secret")

    assert_that(calls).is_equal_to([f"POST {PUBLIC_API_AUTHORIZE_ROUTE}"])


@pytest.mark.parametrize(
    "body",
    [
        pytest.param([{"access_token": "in-a-list"}], id="json_array"),
        pytest.param("plain-string", id="json_string"),
        pytest.param(42, id="json_number"),
    ],
)
def test_raises_when_body_is_not_an_object(httpx_mock: HTTPXMock, body: object) -> None:
    """Клиент сообщает об ошибке разбора, если тело ответа IAM не JSON-объект."""
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        json=body,
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_InvalidJsonResponseError):
        client.authorize("boxed-key", "boxed-secret")


def test_raises_when_access_token_is_not_a_string(httpx_mock: HTTPXMock) -> None:
    """Клиент сообщает об ошибке разбора, если токен доступа пришел не строкой."""
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        json=dict[str, object]({"access_token": 12345, "expires_in": 3600}),
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_InvalidJsonResponseError):
        client.authorize("numeric-key", "numeric-secret")


def test_raises_when_lifetime_is_not_a_number(httpx_mock: HTTPXMock) -> None:
    """Клиент сообщает об ошибке разбора, если срок жизни пришел строкой."""
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        json=dict[str, object]({"access_token": "stringly-typed-token", "expires_in": "3600"}),
    )

    with IAM_HttpClient(constants.IAM_URL) as client, pytest.raises(IAM_InvalidJsonResponseError):
        client.authorize("stringly-key", "stringly-secret")


def test_ignores_unknown_authorization_response_fields(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{constants.IAM_URL}{PUBLIC_API_AUTHORIZE_ROUTE}",
        method="POST",
        json=dict[str, object]({"access_token": "synthetic", "expires_in": 130, "unknown": "server extension"}),
    )

    with IAM_HttpClient(constants.IAM_URL) as client:
        auth_data = client.authorize("extension-key", "extension-secret")

    assert_that(auth_data.expires_in).is_equal_to(130)
