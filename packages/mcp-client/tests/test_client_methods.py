from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from assertpy import assert_that
from mcp import McpError
from mcp_client.client import BaseAsyncMCPClient
from mcp_client.connection_handlers import stdio_connection_handler
from mcp_client.exceptions import SessionNotInititalizedError, StreamInitFailureError

from .mock_server import EXPECTED_TOOL_NAMES

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp_client.custom_types import AsyncOperation

    from .support import ConnectionHandlerFactory


async def test_lists_available_tools(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.list_tools()
    assert_that([tool.name for tool in result.tools]).contains_only(*EXPECTED_TOOL_NAMES)


async def test_returns_server_capabilities(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.get_server_capabilities()
    assert_that(result is not None and result.tools is not None).is_true()


async def test_confirms_ping_response(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.ping_server()
    assert_that(result).is_true()


@pytest.mark.parametrize(("name", "arguments"), [("absent_tool", {}), ("add", {}), ("add", {"a": "wrong", "b": 7})])
async def test_reports_invalid_tool_requests(
    connection_handler: ConnectionHandlerFactory,
    name: str,
    arguments: dict[str, object],
) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.call_tool(name, arguments)
    assert_that(result.is_error).is_true()


async def test_returns_arithmetic_result(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.call_tool("add", {"a": -19, "b": 24})
    assert_that(result.text_content()).is_equal_to("5")


async def test_limits_slow_tool_reads(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        with pytest.raises(McpError, match="Timed out"):
            await client.call_tool("slow_tool", {"duration_seconds": 0.4}, read_timeout_seconds=0.05)


async def test_preserves_nested_arguments(connection_handler: ConnectionHandlerFactory) -> None:
    arguments = {"strange-key/": ["snow 雪", 37, {"flag": True}]}
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.call_tool("echo_arguments_and_metadata_structured", {"arguments": arguments})
    assert_that(result.structured_content).contains_entry(received_arguments=arguments)


async def test_passes_request_metadata(connection_handler: ConnectionHandlerFactory) -> None:
    metadata = {"request_id": "mcp-613", "priority": 17}
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.call_tool("echo_arguments_and_metadata_structured", metadata=metadata)
    assert_that(result.structured_content).contains_entry(received_metadata=metadata)


async def test_preserves_response_metadata(connection_handler: ConnectionHandlerFactory) -> None:
    metadata = {"trace": "mcp/response-47"}
    async with BaseAsyncMCPClient(connection_handler) as client:
        result = await client.call_tool("echo_arguments_and_metadata_structured", metadata=metadata)
    assert_that(result.metadata).is_equal_to(metadata)


async def test_lists_no_tools_on_empty_server() -> None:
    path = Path(__file__).with_name("mock_server_empty.py")
    async with BaseAsyncMCPClient(stdio_connection_handler(sys.executable, [str(path)])) as client:
        result = await client.list_tools()
    assert_that(result.tools).is_empty()


async def test_reports_server_termination(mock_server_path: str) -> None:
    async with BaseAsyncMCPClient(stdio_connection_handler(sys.executable, [mock_server_path])) as client:
        with pytest.raises(McpError, match="Connection closed"):
            await client.call_tool("crash_server")


async def test_reconnects_after_close(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler) as client:
        await client.ping_server()
        await client.aclose()
        result = await client.call_tool("multiply", {"a": 6, "b": 7})
    assert_that(result.text_content()).is_equal_to("42")


async def test_rejects_transport_without_streams() -> None:
    @asynccontextmanager
    async def empty_transport() -> AsyncIterator[None]:
        yield None

    factory = cast("ConnectionHandlerFactory", empty_transport)
    async with BaseAsyncMCPClient(factory) as client:
        with pytest.raises(StreamInitFailureError):
            await client.list_tools()


async def test_reports_connection_decorator_that_does_not_initialize_session(
    connection_handler: ConnectionHandlerFactory,
) -> None:
    def suppress(operation: AsyncOperation[None]) -> AsyncOperation[None]:
        del operation

        async def skipped() -> None:
            return

        return skipped

    def custom_option(client: BaseAsyncMCPClient) -> None:
        client.add_connect_decorator(suppress)

    async with BaseAsyncMCPClient(connection_handler, custom_option) as client:
        with pytest.raises(SessionNotInititalizedError):
            await client.ping_server()
