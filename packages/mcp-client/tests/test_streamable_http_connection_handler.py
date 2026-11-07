from __future__ import annotations

from typing import TYPE_CHECKING, Unpack

import httpx
import pytest
from assertpy import assert_that
from http_client import AsyncHttpClient
from http_client.options import with_auth, with_default_headers
from mcp_client.client import BaseAsyncMCPClient
from mcp_client.connection_handlers import streamable_http_connection_handler

if TYPE_CHECKING:
    from multiprocessing.process import BaseProcess

    from http_client.client import BaseHttpClient
    from http_client.types import AsyncSendMethod, SendOptions


async def test_uses_workspace_http_client(
    http_server: BaseProcess,
    http_server_url: str,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    requests: list[httpx.Request] = []

    def capture(request: httpx.Request) -> None:
        requests.append(request)

    def custom_option(client: BaseHttpClient) -> None:
        client.add_request_hook(capture)

    async with (
        AsyncHttpClient(http_server_url, with_default_headers({"x-client": "workspace"}), custom_option) as transport,
        BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client,
    ):
        await client.call_tool("add", {"a": 3, "b": 9})
    assert_that([request.headers["x-client"] for request in requests]).is_not_empty().contains_only("workspace")


async def test_keeps_raw_httpx_client_owned_by_caller(
    http_server: BaseProcess,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    async with httpx.AsyncClient() as transport:
        async with BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client:
            await client.ping_server()
        closed = transport.is_closed
    assert_that(closed).is_false()


async def test_reports_refused_http_connection() -> None:
    async with BaseAsyncMCPClient(streamable_http_connection_handler("http://127.0.0.1:1/mcp")) as client:
        with pytest.raises(ExceptionGroup) as error:
            await client.list_tools()
    assert_that(str(error.value)).contains("TaskGroup")


async def test_preserves_workspace_query_parameters(
    http_server: BaseProcess,
    http_server_url: str,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    requests: list[httpx.Request] = []

    def custom_option(client: BaseHttpClient) -> None:
        client.add_request_hook(requests.append)

    async with AsyncHttpClient(http_server_url, custom_option) as transport:
        transport.client.params = httpx.QueryParams({"origin": "workspace"})
        async with BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client:
            await client.ping_server()
    assert_that([request.url.params["origin"] for request in requests]).is_not_empty().contains_only("workspace")


async def test_preserves_workspace_cookies(
    http_server: BaseProcess,
    http_server_url: str,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    requests: list[httpx.Request] = []

    def custom_option(client: BaseHttpClient) -> None:
        client.add_request_hook(requests.append)

    async with AsyncHttpClient(http_server_url, custom_option) as transport:
        transport.client.cookies.set("qa-session", "cookie-from-workspace", domain="127.0.0.1")
        async with BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client:
            await client.ping_server()
    assert_that([request.headers["cookie"] for request in requests]).contains_only("qa-session=cookie-from-workspace")


async def test_preserves_workspace_authentication(
    http_server: BaseProcess,
    http_server_url: str,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    requests: list[httpx.Request] = []

    def custom_option(client: BaseHttpClient) -> None:
        client.add_request_hook(requests.append)

    account = ("mcp-user", "local-fixture")
    async with (
        AsyncHttpClient(http_server_url, with_auth(httpx.BasicAuth(*account)), custom_option) as transport,
        BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client,
    ):
        await client.ping_server()
    assert_that([request.headers["authorization"] for request in requests]).contains_only(
        "Basic bWNwLXVzZXI6bG9jYWwtZml4dHVyZQ=="
    )


async def test_preserves_workspace_send_decorators(
    http_server: BaseProcess,
    http_server_url: str,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    observed: list[bool] = []

    def decorate(operation: AsyncSendMethod) -> AsyncSendMethod:
        async def send(request: httpx.Request, **options: Unpack[SendOptions]) -> httpx.Response:
            observed.append(options.get("stream", False))
            return await operation(request, **options)

        return send

    def custom_option(client: BaseHttpClient) -> None:
        client.add_send_decorator(decorate)

    async with (
        AsyncHttpClient(http_server_url, custom_option) as transport,
        BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client,
    ):
        await client.call_tool("add", {"a": 47, "b": 19})
    expected_streaming = True
    assert_that(observed).is_not_empty().contains_only(expected_streaming)


async def test_keeps_workspace_client_owned_by_caller(
    http_server: BaseProcess,
    http_server_url: str,
    mcp_endpoint_url: str,
) -> None:
    if not http_server.is_alive():
        raise RuntimeError
    async with AsyncHttpClient(http_server_url) as transport:
        async with BaseAsyncMCPClient(streamable_http_connection_handler(mcp_endpoint_url, transport)) as client:
            await client.ping_server()
        closed = transport.client.is_closed
    assert_that(closed).is_false()
