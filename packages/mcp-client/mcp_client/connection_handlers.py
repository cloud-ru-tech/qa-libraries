"""Transport factories for MCP clients."""

from __future__ import annotations

from contextlib import asynccontextmanager, nullcontext
from typing import TYPE_CHECKING, TypedDict, Unpack

import httpx2
from http_client import AsyncHttpClient
from httpx2._client import UseClientDefault
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from httpx2._types import (
        AuthTypes,
        CookieTypes,
        HeaderTypes,
        QueryParamTypes,
        RequestContent,
        RequestFiles,
        TimeoutTypes,
    )

    from .custom_types import AsyncConnectionHandler, ConnectionHandlerFactory, Streams


class _BuildRequestOptions(TypedDict, total=False):
    content: RequestContent | None
    data: Mapping[str, object] | None
    files: RequestFiles | None
    json: object
    params: QueryParamTypes | None
    headers: HeaderTypes | None
    cookies: CookieTypes | None
    timeout: TimeoutTypes | UseClientDefault
    extensions: Mapping[str, object] | None


class _HttpClientAdapter(httpx2.AsyncClient):
    def __init__(self, client: AsyncHttpClient) -> None:
        super().__init__(max_redirects=client.client.max_redirects)
        self._workspace_client = client

    def build_request(
        self,
        method: str,
        url: httpx2.URL | str,
        **options: Unpack[_BuildRequestOptions],
    ) -> httpx2.Request:
        return self._workspace_client.client.build_request(method, url, **options)

    async def send(
        self,
        request: httpx2.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | UseClientDefault | None = httpx2.USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = httpx2.USE_CLIENT_DEFAULT,
    ) -> httpx2.Response:
        return await self._workspace_client.send(
            request,
            stream=stream,
            auth=None if isinstance(auth, UseClientDefault) else auth,
            follow_redirects=None if isinstance(follow_redirects, UseClientDefault) else follow_redirects,
        )


def stdio_connection_handler(
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> ConnectionHandlerFactory:
    """Create a transport factory running a local stdio server.

    :param command: Executable starting the server.
    :param args: Command arguments.
    :param env: Additional subprocess environment.
    :return: Factory of transport context managers.
    """

    def handler() -> AsyncConnectionHandler:
        parameters = StdioServerParameters(command=command, args=args or [], env=env)
        return stdio_client(parameters)

    return handler


def streamable_http_connection_handler(
    url: str,
    http_client: httpx2.AsyncClient | AsyncHttpClient | None = None,
) -> ConnectionHandlerFactory:
    """Create an HTTP transport retaining workspace authentication and decorators.

    :param url: MCP endpoint URL.
    :param http_client: Optional externally owned raw or workspace HTTP client.
    :return: Factory of transport context managers.
    """

    @asynccontextmanager
    async def handler() -> AsyncIterator[Streams]:
        transport = (
            _HttpClientAdapter(http_client) if isinstance(http_client, AsyncHttpClient) else nullcontext(http_client)
        )
        async with transport as client, streamable_http_client(url, http_client=client) as streams:
            yield streams

    return handler
