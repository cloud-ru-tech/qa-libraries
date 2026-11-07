from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from assertpy import assert_that
from mcp_client.client import BaseAsyncMCPClient
from mcp_client.options import with_default_metadata, with_logger, with_structlogger

if TYPE_CHECKING:
    from io import StringIO
    from logging import Logger

    from .support import ConnectionHandlerFactory


@dataclass
class StructuredLog:
    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **values: object) -> None:
        self.entries.append((event, values))


async def test_logs_request_fields(
    connection_handler: ConnectionHandlerFactory,
    string_logger: tuple[Logger, StringIO],
) -> None:
    logger, output = string_logger
    async with BaseAsyncMCPClient(connection_handler, with_logger(logger)) as client:
        await client.call_tool("add", {"a": 29, "b": 11}, metadata={"request_id": "req-815"})
    assert_that(output.getvalue()).contains("tool_name=add", "'a': 29", "'b': 11", "'request_id': 'req-815'")


async def test_logs_response_fields(
    connection_handler: ConnectionHandlerFactory,
    string_logger: tuple[Logger, StringIO],
) -> None:
    logger, output = string_logger
    async with BaseAsyncMCPClient(connection_handler, with_logger(logger)) as client:
        await client.call_tool("subtract", {"a": 31, "b": 12})
    assert_that(output.getvalue()).contains("MCP response: tool_name=subtract", "is_success=True", "19")


async def test_masks_nested_request_values(
    connection_handler: ConnectionHandlerFactory,
    string_logger: tuple[Logger, StringIO],
) -> None:
    logger, output = string_logger
    async with BaseAsyncMCPClient(connection_handler, with_logger(logger, ["password"])) as client:
        await client.call_tool("echo_arguments_and_metadata_structured", {"arguments": {"password": "nested-secret"}})
    assert_that(output.getvalue()).does_not_contain("nested-secret")


async def test_masks_default_metadata_values(
    connection_handler: ConnectionHandlerFactory,
    string_logger: tuple[Logger, StringIO],
) -> None:
    logger, output = string_logger
    async with BaseAsyncMCPClient(
        connection_handler,
        with_default_metadata({"token": "hidden-default"}),
        with_logger(logger, ["token"]),
    ) as client:
        await client.call_tool("add", {"a": 2, "b": 3})
    assert_that(output.getvalue()).does_not_contain("hidden-default")


async def test_masks_response_content(
    connection_handler: ConnectionHandlerFactory,
    string_logger: tuple[Logger, StringIO],
) -> None:
    logger, output = string_logger
    async with BaseAsyncMCPClient(connection_handler, with_logger(logger, ["secret-output"])) as client:
        await client.call_tool("echo_with_metadata", {"message": "secret-output"})
    assert_that(output.getvalue()).does_not_contain("secret-output")


async def test_logs_structured_request_fields(connection_handler: ConnectionHandlerFactory) -> None:
    logger = StructuredLog()
    async with BaseAsyncMCPClient(connection_handler, with_structlogger(logger)) as client:
        await client.call_tool("multiply", {"a": 8, "b": 7}, metadata={"request_id": "request-73"})
    assert_that(logger.entries[0]).is_equal_to(
        (
            "mcp request sent",
            {"tool_name": "multiply", "arguments": {"a": 8, "b": 7}, "metadata": {"request_id": "request-73"}},
        )
    )


async def test_logs_structured_response_status(connection_handler: ConnectionHandlerFactory) -> None:
    logger = StructuredLog()
    async with BaseAsyncMCPClient(connection_handler, with_structlogger(logger)) as client:
        await client.call_tool("fail_tool")
    assert_that(logger.entries[1][1]).contains_entry(tool_name="fail_tool", is_success=False)


async def test_masks_structured_secrets(connection_handler: ConnectionHandlerFactory) -> None:
    logger = StructuredLog()
    async with BaseAsyncMCPClient(connection_handler, with_structlogger(logger, ["token", "body-secret"])) as client:
        await client.call_tool("echo_with_metadata", {"message": "body-secret"}, metadata={"token": "metadata-secret"})
    assert_that(str(logger.entries)).does_not_contain("body-secret", "metadata-secret")
