"""Transport factories for MCP clients."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, TypedDict, Unpack, cast

import httpx
from http_client import AsyncHttpClient
from httpx._client import UseClientDefault
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from httpx._types import (
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


class _HttpClientAdapter(httpx.AsyncClient):
    def __init__(self, client: AsyncHttpClient) -> None:
        super().__init__()
        self._workspace_client = client

    def build_request(
        self,
        method: str,
        url: httpx.URL | str,
        **options: Unpack[_BuildRequestOptions],
    ) -> httpx.Request:
        return self._workspace_client.client.build_request(method, url, **options)

    async def send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | UseClientDefault | None = httpx.USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = httpx.USE_CLIENT_DEFAULT,
    ) -> httpx.Response:
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
        return cast("AsyncConnectionHandler", stdio_client(parameters))

    return handler


def streamable_http_connection_handler(
    url: str,
    http_client: httpx.AsyncClient | AsyncHttpClient | None = None,
) -> ConnectionHandlerFactory:
    """Create an HTTP transport retaining workspace authentication and decorators.

    :param url: MCP endpoint URL.
    :param http_client: Optional externally owned raw or workspace HTTP client.
    :return: Factory of transport context managers.
    """

    @asynccontextmanager
    async def handler() -> AsyncIterator[Streams]:
        if isinstance(http_client, AsyncHttpClient):
            async with (
                _HttpClientAdapter(http_client) as adapter,
                streamable_http_client(url, http_client=adapter) as (reader, writer, _),
            ):
                yield reader, writer
        else:
            async with streamable_http_client(url, http_client=http_client) as (reader, writer, _):
                yield reader, writer

    return handler
