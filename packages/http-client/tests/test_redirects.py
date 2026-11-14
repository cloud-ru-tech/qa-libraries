import httpx
import pytest
from assertpy import assert_that
from http_client.options import with_follow_redirects
from httpx import codes
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


def add_hop(httpx_mock: HTTPXMock, from_url: str, to_url: str) -> None:
    """Register one redirect step."""
    httpx_mock.add_response(
        url=from_url,
        method="GET",
        status_code=codes.FOUND,
        headers={"Location": to_url},
    )


def test_anonymous_call_follows_redirects(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """anonymous=True preserves follow_redirects supplied by the call.

    Regression: the anonymous _send branch did not pass follow_redirects,
    so the httpx.Client setting was always used.
    """
    add_hop(httpx_mock, "https://example.com/start", "https://example.com/final")
    httpx_mock.add_response(url="https://example.com/final", method="GET", status_code=codes.OK)
    client = new_client("https://example.com")

    response = client.get("/start", follow_redirects=True, anonymous=True)

    assert_that(str(response.url)).is_equal_to("https://example.com/final")


def test_response_keeps_redirect_in_history(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """A followed redirect remains in the response history."""
    add_hop(httpx_mock, "https://example.com/old", "https://example.com/new")
    httpx_mock.add_response(url="https://example.com/new", method="GET", status_code=codes.OK)
    client = new_client("https://example.com")

    response = client.get("/old", follow_redirects=True)

    assert_that(response.history).is_length(1)


async def test_async_anonymous_call_follows_redirects(
    httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    """anonymous=True preserves follow_redirects in the asynchronous client too."""
    add_hop(httpx_mock, "https://example.com/start", "https://example.com/final")
    httpx_mock.add_response(url="https://example.com/final", method="GET", status_code=codes.OK)
    client = new_async_client("https://example.com")

    response = await client.get("/start", follow_redirects=True, anonymous=True)

    assert_that(str(response.url)).is_equal_to("https://example.com/final")


def test_client_option_enables_following_redirects(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """with_follow_redirects enables redirect following for all calls."""
    add_hop(httpx_mock, "https://example.com/entry", "https://example.com/target")
    httpx_mock.add_response(url="https://example.com/target", method="GET", status_code=codes.OK)
    client = new_client("https://example.com", with_follow_redirects())

    response = client.get("/entry")

    assert_that(str(response.url)).is_equal_to("https://example.com/target")


def test_client_stops_after_max_redirects(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """A chain longer than max_redirects ends with an error."""
    add_hop(httpx_mock, "https://example.com/one", "https://example.com/two")
    add_hop(httpx_mock, "https://example.com/two", "https://example.com/three")
    client = new_client("https://example.com", with_follow_redirects(max_redirects=1))

    with pytest.raises(httpx.TooManyRedirects):
        client.get("/one")


def test_request_without_follow_redirects_returns_redirect(
    httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Return the redirect response when redirect following is disabled."""
    add_hop(httpx_mock, "https://example.com/short", "https://example.com/long")
    client = new_client("https://example.com")

    response = client.get("/short")

    assert_that(response.status_code).is_equal_to(codes.FOUND)
