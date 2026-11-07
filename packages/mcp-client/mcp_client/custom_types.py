from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage

if TYPE_CHECKING:
    from .results import ToolCallResponse

type Streams = tuple[MemoryObjectReceiveStream[SessionMessage | Exception], MemoryObjectSendStream[SessionMessage]]
type AsyncConnectionHandler = AbstractAsyncContextManager[Streams]
type ConnectionHandlerFactory = Callable[[], AsyncConnectionHandler]
type AsyncOperation[T] = Callable[[], Awaitable[T]]
type AsyncDecorator[T] = Callable[[AsyncOperation[T]], AsyncOperation[T]]
type MetadataProvider = Callable[[], Mapping[str, object]]


class RequestHook(Protocol):
    """Observe a tool request before execution."""

    def __call__(
        self, *, tool_name: str, arguments: Mapping[str, object], metadata: Mapping[str, object] | None
    ) -> None:
        """Handle request values without changing the request."""
        ...


class ResponseHook(Protocol):
    """Observe a completed tool request."""

    def __call__(self, *, tool_name: str, response: ToolCallResponse) -> None:
        """Handle a tool response."""
        ...


class StructuredLogger(Protocol):
    """Accept structured MCP log entries."""

    def info(self, event: str, **values: object) -> object:
        """Write a structured informational event."""
        ...
