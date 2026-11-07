from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that
from mcp import McpError
from mcp_client.client import BaseAsyncMCPClient
from mcp_client.options import with_default_metadata, with_read_timeout

if TYPE_CHECKING:
    from .support import ConnectionHandlerFactory


async def test_sends_default_metadata(connection_handler: ConnectionHandlerFactory) -> None:
    metadata = {"environment": "local-qa", "version": 31}
    async with BaseAsyncMCPClient(connection_handler, with_default_metadata(metadata)) as client:
        result = await client.call_tool("echo_arguments_and_metadata_structured")
    assert_that(result.structured_content).contains_entry(received_metadata=metadata)


async def test_overrides_default_metadata_with_call_values(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler, with_default_metadata({"priority": 4, "build": "abc"})) as client:
        result = await client.call_tool("echo_arguments_and_metadata_structured", metadata={"priority": 9})
    expected = {"priority": 9, "build": "abc"}
    assert_that(result.structured_content).contains_entry(received_metadata=expected)


async def test_applies_default_read_timeout(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler, with_read_timeout(0.04)) as client:
        with pytest.raises(McpError, match="Timed out"):
            await client.call_tool("slow_tool", {"duration_seconds": 0.3})


async def test_overrides_default_read_timeout(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler, with_read_timeout(0.01)) as client:
        result = await client.call_tool("slow_tool", {"duration_seconds": 0.08}, read_timeout_seconds=1)
    assert_that(result.text_content()).is_equal_to("Slept for 0.08 seconds")


async def test_keeps_temporary_metadata_separate(connection_handler: ConnectionHandlerFactory) -> None:
    async with BaseAsyncMCPClient(connection_handler, with_default_metadata({"scope": "original"})) as original:
        async with original.with_options(with_default_metadata({"scope": "temporary"})) as temporary:
            await temporary.call_tool("echo_arguments_and_metadata_structured")
        result = await original.call_tool("echo_arguments_and_metadata_structured")
    expected = {"scope": "original"}
    assert_that(result.structured_content).contains_entry(received_metadata=expected)
