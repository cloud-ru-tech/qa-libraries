from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from .results import LiveSSHResult, SSHResult

type OutputCallback = Callable[[str], None]
type InterruptCallback = Callable[[str], bool]
type SyncOperation[T] = Callable[[], T]
type AsyncOperation[T] = Callable[[], Awaitable[T]]


class OperationDecorator(Protocol):
    """Wrap an operation while preserving its parameters and result."""

    def __call__[T](self, operation: Callable[[], T]) -> Callable[[], T]:
        """Return a wrapped operation.

        :param operation: Deferred connection or command operation.
        :return: Operation with the same result type.
        """
        ...


class RequestHook(Protocol):
    """Observe an SSH request."""

    def __call__(self, *, host: str, port: int, username: str | None, command: str) -> None:
        """Handle request values."""
        ...


class ResponseHook(Protocol):
    """Observe an SSH command result."""

    def __call__(self, *, host: str, command: str, result: SSHResult | LiveSSHResult) -> None:
        """Handle completed command output."""
        ...


class StructuredLogger(Protocol):
    """Accept structured SSH log entries."""

    def info(self, event: str, **values: object) -> object:
        """Write a structured informational event."""
        ...


class Closeable(Protocol):
    """Close a synchronous transport."""

    def close(self) -> None:
        """Release the transport."""
        ...


class AsyncCloseable(Closeable, Protocol):
    """Wait for transport shutdown."""

    async def wait_closed(self) -> None:
        """Wait until transport resources are released."""
        ...


class ExecuteOptions(TypedDict, total=False):
    """Keyword settings for a command."""

    timeout: float | None
    raise_for_status: bool


class LiveExecuteOptions(ExecuteOptions, total=False):
    """Keyword settings for a streaming command."""

    stdout_callback: OutputCallback | None
    stderr_callback: OutputCallback | None
    interrupt_stdout_callback: InterruptCallback | None
    interrupt_stderr_callback: InterruptCallback | None
