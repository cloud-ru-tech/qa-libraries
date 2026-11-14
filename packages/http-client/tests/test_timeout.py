from typing import cast

from assertpy import assert_that
from http_client.options import with_timeout
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory

type TimeoutExtension = dict[str, float | None]

DEFAULT_TIMEOUT: TimeoutExtension = {"connect": 60, "read": 60, "write": 60, "pool": 60}
DISABLED_TIMEOUT: TimeoutExtension = {"connect": None, "read": None, "write": None, "pool": None}


def test_get_uses_client_default_timeout(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """get() uses the client timeout when timeout is not specified rather than disabling it.

    Regression: the timeout=None default overwrote the client timeout (Timeout(None) in httpx),
    allowing the request to hang indefinitely.
    """
    httpx_mock.add_response(url="https://example.com/v2/", method="GET", status_code=200)
    client = new_client("https://example.com")

    client.get("/v2/")

    assert_that(_sent_timeout(httpx_mock)).is_equal_to(DEFAULT_TIMEOUT)


def test_get_uses_timeout_given_to_call(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Apply the timeout explicitly specified for the request."""
    httpx_mock.add_response(url="https://example.com/v2/", method="GET", status_code=200)
    client = new_client("https://example.com")

    client.get("/v2/", timeout=5)

    assert_that(_sent_timeout(httpx_mock)).is_equal_to({"connect": 5, "read": 5, "write": 5, "pool": 5})


def test_get_uses_timeout_given_to_client(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """with_timeout sets the timeout for requests without an explicit timeout."""
    httpx_mock.add_response(url="https://example.com/v2/", method="GET", status_code=200)
    client = new_client("https://example.com", with_timeout(30))

    client.get("/v2/")

    assert_that(_sent_timeout(httpx_mock)).is_equal_to({"connect": 30, "read": 30, "write": 30, "pool": 30})


def test_explicit_none_disables_timeout(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """An explicit timeout=None deliberately disables the timeout."""
    httpx_mock.add_response(url="https://example.com/v2/", method="GET", status_code=200)
    client = new_client("https://example.com")

    client.get("/v2/", timeout=None)

    assert_that(_sent_timeout(httpx_mock)).is_equal_to(DISABLED_TIMEOUT)


def test_post_uses_client_default_timeout(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """post() also uses the client timeout when timeout is not specified."""
    httpx_mock.add_response(url="https://example.com/v2/", method="POST", status_code=201)
    client = new_client("https://example.com")

    client.post("/v2/", json={"a": 1})

    assert_that(_sent_timeout(httpx_mock)).is_equal_to(DEFAULT_TIMEOUT)


def test_stream_uses_client_default_timeout(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """stream(method, url) uses the client timeout when timeout is not specified."""
    httpx_mock.add_response(url="https://example.com/data", method="GET", status_code=200, content=b"x")
    client = new_client("https://example.com")

    with client.stream("GET", "/data") as response:
        response.read()

    assert_that(_sent_timeout(httpx_mock)).is_equal_to(DEFAULT_TIMEOUT)


async def test_async_get_uses_client_default_timeout(
    httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    """Asynchronous get() uses the client timeout when timeout is not specified."""
    httpx_mock.add_response(url="https://example.com/v2/", method="GET", status_code=200)
    client = new_async_client("https://example.com")

    await client.get("/v2/")

    assert_that(_sent_timeout(httpx_mock)).is_equal_to(DEFAULT_TIMEOUT)


def _sent_timeout(httpx_mock: HTTPXMock) -> TimeoutExtension:
    extensions = cast("dict[str, TimeoutExtension]", httpx_mock.get_requests()[0].extensions)
    return extensions["timeout"]
