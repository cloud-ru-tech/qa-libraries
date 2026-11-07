import httpx
import pytest
from assertpy import assert_that
from http_client.options import with_follow_redirects
from httpx import codes
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


def add_hop(httpx_mock: HTTPXMock, from_url: str, to_url: str) -> None:
    """Зарегистрировать один шаг редиректа."""
    httpx_mock.add_response(
        url=from_url,
        method="GET",
        status_code=codes.FOUND,
        headers={"Location": to_url},
    )


def test_anonymous_call_follows_redirects(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """anonymous=True не отменяет follow_redirects, переданный в вызов.

    Регрессия: анонимная ветка _send не передавала follow_redirects,
    из-за чего всегда использовалась настройка httpx.Client.
    """
    add_hop(httpx_mock, "https://example.com/start", "https://example.com/final")
    httpx_mock.add_response(url="https://example.com/final", method="GET", status_code=codes.OK)
    client = new_client("https://example.com")

    response = client.get("/start", follow_redirects=True, anonymous=True)

    assert_that(str(response.url)).is_equal_to("https://example.com/final")


def test_response_keeps_redirect_in_history(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Пройденный редирект остаётся в истории ответа."""
    add_hop(httpx_mock, "https://example.com/old", "https://example.com/new")
    httpx_mock.add_response(url="https://example.com/new", method="GET", status_code=codes.OK)
    client = new_client("https://example.com")

    response = client.get("/old", follow_redirects=True)

    assert_that(response.history).is_length(1)


async def test_async_anonymous_call_follows_redirects(
    httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    """anonymous=True не отменяет follow_redirects и в асинхронном клиенте."""
    add_hop(httpx_mock, "https://example.com/start", "https://example.com/final")
    httpx_mock.add_response(url="https://example.com/final", method="GET", status_code=codes.OK)
    client = new_async_client("https://example.com")

    response = await client.get("/start", follow_redirects=True, anonymous=True)

    assert_that(str(response.url)).is_equal_to("https://example.com/final")


def test_client_option_enables_following_redirects(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """with_follow_redirects включает следование редиректам для всех вызовов."""
    add_hop(httpx_mock, "https://example.com/entry", "https://example.com/target")
    httpx_mock.add_response(url="https://example.com/target", method="GET", status_code=codes.OK)
    client = new_client("https://example.com", with_follow_redirects())

    response = client.get("/entry")

    assert_that(str(response.url)).is_equal_to("https://example.com/target")


def test_client_stops_after_max_redirects(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Цепочка длиннее max_redirects обрывается ошибкой."""
    add_hop(httpx_mock, "https://example.com/one", "https://example.com/two")
    add_hop(httpx_mock, "https://example.com/two", "https://example.com/three")
    client = new_client("https://example.com", with_follow_redirects(max_redirects=1))

    with pytest.raises(httpx.TooManyRedirects):
        client.get("/one")


def test_request_without_follow_redirects_returns_redirect(
    httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Без включённого следования клиент возвращает сам ответ-редирект."""
    add_hop(httpx_mock, "https://example.com/short", "https://example.com/long")
    client = new_client("https://example.com")

    response = client.get("/short")

    assert_that(response.status_code).is_equal_to(codes.FOUND)
