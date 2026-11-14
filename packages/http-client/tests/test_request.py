from typing import cast

from assertpy import assert_that
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


def test_request_sends_given_method(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """request() sends the request with the supplied method."""
    httpx_mock.add_response(url="https://example.com/api/resource", method="PATCH", status_code=200)
    client = new_client("https://example.com")

    client.request("PATCH", "/api/resource", json={"field": "value"})

    assert_that(httpx_mock.get_requests()[0].method).is_equal_to("PATCH")


def test_request_returns_response_body(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """request() returns the parsed response body."""
    payload: dict[str, bool] = {"patched": True}
    httpx_mock.add_response(url="https://example.com/api/resource", method="PATCH", json=payload)
    client = new_client("https://example.com")

    response = client.request("PATCH", "/api/resource", json={"field": "value"})

    assert_that(cast("object", response.json())).is_equal_to(payload)


async def test_async_request_sends_given_method(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Asynchronous client request() sends the request with the supplied method."""
    httpx_mock.add_response(url="https://example.com/api/resource", method="DELETE", status_code=204)
    client = new_async_client("https://example.com")

    await client.request("DELETE", "/api/resource")

    assert_that(httpx_mock.get_requests()[0].method).is_equal_to("DELETE")


async def test_async_request_returns_status(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Asynchronous client request() returns the response status code."""
    httpx_mock.add_response(url="https://example.com/api/resource", method="DELETE", status_code=204)
    client = new_async_client("https://example.com")

    response = await client.request("DELETE", "/api/resource")

    assert_that(response.status_code).is_equal_to(204)
