from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import InterruptCallback, OutputCallback
    from .utils.retries import RetryPolicy


@dataclass
class SSHClientConfig:
    """Store connection and command settings."""

    username: str | None = None
    password: str | None = None
    private_key_path: str | None = None
    known_hosts: str | None = None
    timeout: float = 30
    connection_timeout: float | None = None
    connection_retry: RetryPolicy | None = None
    command_retry: RetryPolicy | None = None
    live_stdout_callback: OutputCallback | None = None
    live_stderr_callback: OutputCallback | None = None


@dataclass
class ExecutionSettings:
    """Group command settings passed to execution helpers."""

    timeout: float | None = None
    raise_for_status: bool = False
    stdout_callback: OutputCallback | None = None
    stderr_callback: OutputCallback | None = None
    interrupt_stdout_callback: InterruptCallback | None = None
    interrupt_stderr_callback: InterruptCallback | None = None
