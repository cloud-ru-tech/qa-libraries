from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that
from mcp_client.client import BaseAsyncMCPClient
from mcp_client.options import retry_if_connection_fails, retry_if_tool_calling_fails
from tenacity import RetryError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from mcp_client.custom_types import Streams
    from mcp_client.results import ToolCallResponse

    from .support import ConnectionHandlerFactory


class TemporaryConnectionError(ConnectionError):
    pass


@dataclass
class FlakyConnection:
    factory: ConnectionHandlerFactory
    remaining_failures: int
    attempts: int = 0

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[Streams]:
        self.attempts += 1
        if self.remaining_failures:
            self.remaining_failures -= 1
            raise TemporaryConnectionError
        async with self.factory() as streams:
            yield streams


@dataclass
class FlakyExecution:
    remaining_failures: int
    attempts: int = 0

    def __call__(
        self, operation: Callable[[], Awaitable[ToolCallResponse]]
    ) -> Callable[[], Awaitable[ToolCallResponse]]:
        async def execute() -> ToolCallResponse:
            self.attempts += 1
            if self.remaining_failures:
                self.remaining_failures -= 1
                raise TemporaryConnectionError
            return await operation()

        return execute


async def test_retries_connection_until_success(connection_handler: ConnectionHandlerFactory) -> None:
    connection = FlakyConnection(connection_handler, remaining_failures=2)
    async with BaseAsyncMCPClient(connection, retry_if_connection_fails(3, 0)) as client:
        await client.ping_server()
    assert_that(connection.attempts).is_equal_to(3)


async def test_stops_retrying_connection_at_limit(connection_handler: ConnectionHandlerFactory) -> None:
    connection = FlakyConnection(connection_handler, remaining_failures=4)
    async with BaseAsyncMCPClient(connection, retry_if_connection_fails(2, 0)) as client:
        with pytest.raises(RetryError):
            await client.ping_server()
    assert_that(connection.attempts).is_equal_to(2)


async def test_reraises_connection_error(connection_handler: ConnectionHandlerFactory) -> None:
    connection = FlakyConnection(connection_handler, remaining_failures=2)
    async with BaseAsyncMCPClient(connection, retry_if_connection_fails(1, 0, reraise_exception=True)) as client:
        with pytest.raises(TemporaryConnectionError):
            await client.list_tools()


async def test_retries_tool_call_until_success(connection_handler: ConnectionHandlerFactory) -> None:
    execution = FlakyExecution(remaining_failures=2)

    def custom_option(client: BaseAsyncMCPClient) -> None:
        client.add_execute_decorator(execution)

    async with BaseAsyncMCPClient(connection_handler, retry_if_tool_calling_fails(3, 0), custom_option) as client:
        result = await client.call_tool("add", {"a": 9, "b": 12})
    assert_that(result.text_content()).is_equal_to("21")


async def test_stops_retrying_tool_calls_at_limit(connection_handler: ConnectionHandlerFactory) -> None:
    execution = FlakyExecution(remaining_failures=5)

    def custom_option(client: BaseAsyncMCPClient) -> None:
        client.add_execute_decorator(execution)

    async with BaseAsyncMCPClient(connection_handler, retry_if_tool_calling_fails(2, 0), custom_option) as client:
        with pytest.raises(RetryError):
            await client.call_tool("add", {"a": 1, "b": 2})
    assert_that(execution.attempts).is_equal_to(2)
