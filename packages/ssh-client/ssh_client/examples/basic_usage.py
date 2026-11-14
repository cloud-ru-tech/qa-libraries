"""Command examples with host key verification and connection cleanup."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import structlog

from ssh_client import AsyncSSHClient, SyncSSHClient, options

if TYPE_CHECKING:
    from ssh_client.types import StructuredLogger

logger = logging.getLogger(__name__)


def sync_example() -> None:
    """Run a command with an SSH agent key and the default known_hosts."""
    with SyncSSHClient("localhost", 22, options.with_private_key("qa-user", "/path/to/private/key")) as client:
        result = client.execute("uname -a", timeout=10, raise_for_status=True)
        logger.info("Remote system: %s", result.stdout)


async def async_example() -> None:
    """Run an asynchronous command with an explicit list of trusted servers."""
    async with AsyncSSHClient(
        "localhost",
        22,
        options.with_private_key("qa-user", "/path/to/private/key"),
        options.with_known_hosts("/path/to/known_hosts"),
        options.with_logger(logger),
    ) as client:
        result = await client.execute("uname -a", timeout=10, raise_for_status=True)
        logger.info("Remote system: %s", result.stdout)


def advanced_sync_example() -> None:
    """Pass command lines to a handler and limit reconnects."""
    with SyncSSHClient(
        "localhost",
        22,
        options.with_private_key("qa-user", "/path/to/private/key"),
        options.with_live_execute_callback(lambda line: logger.info("Output: %s", line)),
        options.retry_if_connection_fails(3, 1, reraise_exception=True),
    ) as client:
        result = client.execute_live("printf 'first\\nsecond\\n'", timeout=10, raise_for_status=True)
        logger.info("Command exit status: %s", result.exit_code)


async def advanced_async_example() -> None:
    """Override settings for one command using a separate client copy."""
    async with AsyncSSHClient(
        "localhost",
        22,
        options.with_private_key("qa-user", "/path/to/private/key"),
    ) as client:
        async with client.with_options(options.with_request_timeout(10)) as temporary:
            result = await temporary.execute_live("printf 'one\\ntwo\\n'", raise_for_status=True)
        logger.info("Output: %s", result.stdout_lines)


def structlog_example() -> None:
    """Log a command through structlog with the specified text masked."""
    structured = cast("StructuredLogger", structlog.get_logger())
    with SyncSSHClient(
        "localhost",
        22,
        options.with_private_key("qa-user", "/path/to/private/key"),
        options.with_structlogger(structured, mask_patterns=["sensitive-value"]),
    ) as client:
        result = client.execute("printf 'sensitive-value'", raise_for_status=True)
        logger.info("Command exit status: %s", result.exit_code)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_example()
    asyncio.run(async_example())
    advanced_sync_example()
    asyncio.run(advanced_async_example())
    structlog_example()
