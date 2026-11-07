from collections.abc import Generator

import httpx
from assertpy import assert_that
from http_client.options import with_auth
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


class FalseyAuth(httpx.Auth):
    """Валидный механизм авторизации, который при этом falsey."""

    def __bool__(self) -> bool:
        return False

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        request.headers["X-Auth"] = "from-falsey"
        yield request


def test_applies_falsey_auth_passed_to_call(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Переданный в вызов Auth применяется, даже если он falsey.

    Регрессия: выражение `auth or self.client.auth` подменяло такой объект авторизацией клиента.
    """
    httpx_mock.add_response(status_code=200)
    client = new_client("https://billing.example.com", with_auth(httpx.BasicAuth("ops", "s3cret")))

    client.get("/invoices", auth=FalseyAuth())

    assert_that(httpx_mock.get_requests()[0].headers["X-Auth"]).is_equal_to("from-falsey")


def test_falsey_auth_from_call_replaces_client_auth(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Авторизация клиента не применяется, когда в вызов передан falsey Auth."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://billing.example.com", with_auth(httpx.BasicAuth("ops", "s3cret")))

    client.get("/invoices", auth=FalseyAuth())

    assert_that(httpx_mock.get_requests()[0].headers).does_not_contain_key("authorization")


async def test_async_applies_falsey_auth_passed_to_call(
    httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    """Асинхронный клиент так же применяет falsey Auth из вызова."""
    httpx_mock.add_response(status_code=200)
    client = new_async_client("https://audit.example.com", with_auth(httpx.BasicAuth("sre", "letmein")))

    await client.get("/events", auth=FalseyAuth())

    assert_that(httpx_mock.get_requests()[0].headers["X-Auth"]).is_equal_to("from-falsey")


def test_applies_client_auth_when_call_has_none(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Без явной авторизации в вызове используется авторизация клиента."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://registry.example.com", with_auth(httpx.BasicAuth("bot", "p@ssw0rd")))

    client.get("/images")

    assert_that(httpx_mock.get_requests()[0].headers).contains_key("authorization")


def test_anonymous_call_drops_client_auth(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """anonymous=True отключает авторизацию клиента."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://status.example.com", with_auth(httpx.BasicAuth("admin", "qwerty")))

    client.get("/health", anonymous=True)

    assert_that(httpx_mock.get_requests()[0].headers).does_not_contain_key("authorization")
