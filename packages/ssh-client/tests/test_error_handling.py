from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that
from ssh_client.clients.exceptions import CommandNonZeroExitCodeError

if TYPE_CHECKING:
    from ssh_client import AsyncSSHClient, SyncSSHClient


def test_returns_nonzero_exit_status(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute("printf 'denied' >&2; exit 37")
    assert_that((result.exit_code, result.stderr)).is_equal_to((37, "denied"))


async def test_returns_nonzero_exit_status_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute("printf 'invalid' >&2; exit 29")
    assert_that((result.exit_code, result.stderr)).is_equal_to((29, "invalid"))


def test_raises_for_failed_command(sync_client: SyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError, match="exit code 41: refused"):
        sync_client.execute("printf 'refused' >&2; exit 41", raise_for_status=True)


async def test_raises_for_failed_command_async(async_client: AsyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError, match="exit code 19: blocked"):
        await async_client.execute("printf 'blocked' >&2; exit 19", raise_for_status=True)


def test_captures_missing_command_error(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute("qa_no_such_executable_891")
    assert_that(result.stderr).contains("qa_no_such_executable_891", "not found")


async def test_captures_missing_command_error_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute("qa_no_such_executable_619")
    assert_that(result.stderr).contains("qa_no_such_executable_619", "not found")
