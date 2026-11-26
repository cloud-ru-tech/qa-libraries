from __future__ import annotations

from typing import TYPE_CHECKING

import httpx2
import pytest
from assertpy import assert_that

if TYPE_CHECKING:
    from http_client import BaseHttpClient
    from pytest_httpx2 import HTTPXMock

    from .support.clients import AsyncClientFactory, SyncClientFactory


def test_custom_option_registers_request_hook(httpx2_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    def add_tenant(request: httpx2.Request) -> None:
        request.headers["X-Tenant-ID"] = "payments"

    def tenant_option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_tenant)

    httpx2_mock.add_response()
    client = new_client("https://catalog.test", tenant_option)

    response = client.get("/items")

    assert_that(response.request.headers["X-Tenant-ID"]).is_equal_to("payments")


async def test_custom_option_registers_async_request_hook(
    httpx2_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    async def add_region(request: httpx2.Request) -> None:
        request.headers["X-Region"] = "west"

    def region_option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_region)

    httpx2_mock.add_response()
    client = new_async_client("https://inventory.test", region_option)

    response = await client.get("/stock")

    assert_that(response.request.headers["X-Region"]).is_equal_to("west")


def test_custom_option_registers_response_hook(httpx2_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    received: list[int] = []

    def collect_status(response: httpx2.Response) -> None:
        received.append(response.status_code)

    def collect_option(client: BaseHttpClient) -> None:
        client.add_response_hook(collect_status)

    httpx2_mock.add_response(status_code=httpx2.codes.ACCEPTED)
    client = new_client("https://queue.test", collect_option)

    client.post("/jobs")

    assert_that(received).is_equal_to([httpx2.codes.ACCEPTED])


def test_custom_option_does_not_modify_another_client(httpx2_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    def add_header(request: httpx2.Request) -> None:
        request.headers["X-Client"] = "configured"

    def custom_option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_header)

    new_client("https://first.test", custom_option)
    httpx2_mock.add_response()
    other = new_client("https://second.test")

    response = other.get("/status")

    assert_that(response.request.headers).does_not_contain_key("X-Client")


def test_rejects_hook_registration_after_client_is_initialized(new_client: SyncClientFactory) -> None:
    client = new_client("https://reports.test")

    with pytest.raises(RuntimeError):
        client.add_request_hook(lambda request: request.headers.update({"X-Late": "ignored"}))
