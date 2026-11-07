from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncssh
import paramiko

from ssh_client.clients.exceptions import CommandNonZeroExitCodeError
from ssh_client.results import SSHResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from logging import Logger

CONNECTION_ERRORS = (OSError, paramiko.SSHException, asyncssh.Error)


@dataclass(frozen=True)
class RetryPolicy:
    """Apply bounded retries to connection and command operations."""

    attempts: int = 3
    interval: float = 5
    reraise: bool = False

    def __post_init__(self) -> None:
        """Reject settings that cannot execute a bounded retry."""
        if self.attempts < 1 or self.interval < 0:
            message = "Retry attempts must be positive and interval must be nonnegative"
            raise ValueError(message)

    def connect(self, operation: Callable[[], None]) -> None:
        """Retry a synchronous connection operation.

        :param operation: Connection attempt.
        """
        for attempt in range(self.attempts):
            try:
                operation()
            except CONNECTION_ERRORS:
                if attempt + 1 == self.attempts:
                    if self.reraise:
                        raise
                    return
                time.sleep(self.interval)
            else:
                return

    async def connect_async(self, operation: Callable[[], Awaitable[None]]) -> None:
        """Retry an asynchronous connection operation without blocking the event loop.

        :param operation: Connection attempt.
        """
        for attempt in range(self.attempts):
            try:
                await operation()
            except CONNECTION_ERRORS:
                if attempt + 1 == self.attempts:
                    if self.reraise:
                        raise
                    return
                await asyncio.sleep(self.interval)
            else:
                return

    def execute(self, operation: Callable[[], SSHResult]) -> SSHResult:
        """Retry raised command errors and nonzero exit codes.

        :param operation: Command attempt.
        :return: Successful or final failed command result.
        """
        result = SSHResult("", "Command execution failed after retries", -1)
        for attempt in range(self.attempts):
            try:
                result = operation()
            except (*CONNECTION_ERRORS, CommandNonZeroExitCodeError):
                if attempt + 1 == self.attempts and self.reraise:
                    raise
            else:
                if result.exit_code == 0:
                    return result
            if attempt + 1 < self.attempts:
                time.sleep(self.interval)
        return self._final_result(result)

    async def execute_async(self, operation: Callable[[], Awaitable[SSHResult]]) -> SSHResult:
        """Retry asynchronous commands without blocking the event loop.

        :param operation: Command attempt.
        :return: Successful or final failed command result.
        """
        result = SSHResult("", "Command execution failed after retries", -1)
        for attempt in range(self.attempts):
            try:
                result = await operation()
            except (*CONNECTION_ERRORS, CommandNonZeroExitCodeError):
                if attempt + 1 == self.attempts and self.reraise:
                    raise
            else:
                if result.exit_code == 0:
                    return result
            if attempt + 1 < self.attempts:
                await asyncio.sleep(self.interval)
        return self._final_result(result)

    def _final_result(self, result: SSHResult) -> SSHResult:
        if self.reraise:
            raise CommandNonZeroExitCodeError.from_result(result)
        return result


def prepare_retry_error_context(error: Exception) -> tuple[str, str]:
    """Return the exception name and message.

    :param error: Failed operation exception.
    :return: Exception name and description.
    """
    return type(error).__name__, str(error)


def retry_if_connection_fails(
    retries_attempts_number: int = 3,
    retries_interval_in_seconds: float = 5,
    *,
    reraise_exception: bool = False,
    logger: Logger | None = None,
) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Create a synchronous connection retry decorator.

    :param retries_attempts_number: Maximum attempts.
    :param retries_interval_in_seconds: Delay between attempts.
    :param reraise_exception: Propagate the final connection error.
    :param logger: Optional logger receiving completion records.
    :return: Connection decorator.
    """
    policy = RetryPolicy(retries_attempts_number, retries_interval_in_seconds, reraise=reraise_exception)

    def decorate(operation: Callable[[], None]) -> Callable[[], None]:
        def execute() -> None:
            policy.connect(operation)
            if logger is not None:
                logger.debug("SSH connection retry operation completed")

        return execute

    return decorate


def retry_if_command_fails(
    retries_attempts_number: int = 3,
    retries_interval_in_seconds: float = 5,
    *,
    reraise_exception: bool = False,
    logger: Logger | None = None,
) -> Callable[[Callable[[], SSHResult]], Callable[[], SSHResult]]:
    """Create a synchronous command retry decorator.

    :param retries_attempts_number: Maximum attempts.
    :param retries_interval_in_seconds: Delay between attempts.
    :param reraise_exception: Propagate final command failure.
    :param logger: Optional logger receiving completion records.
    :return: Command decorator.
    """
    policy = RetryPolicy(retries_attempts_number, retries_interval_in_seconds, reraise=reraise_exception)

    def decorate(operation: Callable[[], SSHResult]) -> Callable[[], SSHResult]:
        def execute() -> SSHResult:
            result = policy.execute(operation)
            if logger is not None:
                logger.debug("SSH command retry operation completed with exit code %s", result.exit_code)
            return result

        return execute

    return decorate
