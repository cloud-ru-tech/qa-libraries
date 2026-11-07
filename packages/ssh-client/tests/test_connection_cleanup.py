from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that
from ssh_client.clients.exceptions import CommandNonZeroExitCodeError

from .support import connection_is_closed

if TYPE_CHECKING:
    from ssh_client import AsyncSSHClient, SyncSSHClient


class HookFailureError(RuntimeError):
    pass


def test_closes_connection_after_execute(sync_client: SyncSSHClient) -> None:
    sync_client.execute("printf 'cleanup'")
    assert_that(connection_is_closed(sync_client)).is_true()


async def test_closes_connection_after_execute_async(async_client: AsyncSSHClient) -> None:
    await async_client.execute("printf 'async cleanup'")
    assert_that(connection_is_closed(async_client)).is_true()


def test_closes_connection_after_live_execute(sync_client: SyncSSHClient) -> None:
    sync_client.execute_live("printf 'live cleanup\\n'")
    assert_that(connection_is_closed(sync_client)).is_true()


async def test_closes_connection_after_live_execute_async(async_client: AsyncSSHClient) -> None:
    await async_client.execute_live("printf 'async live cleanup\\n'")
    assert_that(connection_is_closed(async_client)).is_true()


def test_closes_connection_after_command_failure(sync_client: SyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError):
        sync_client.execute("exit 17", raise_for_status=True)
    assert_that(connection_is_closed(sync_client)).is_true()


async def test_closes_connection_after_command_failure_async(async_client: AsyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError):
        await async_client.execute("exit 23", raise_for_status=True)
    assert_that(connection_is_closed(async_client)).is_true()


def test_closes_connection_after_live_command_failure(sync_client: SyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError):
        sync_client.execute_live("exit 43", raise_for_status=True)
    assert_that(connection_is_closed(sync_client)).is_true()


async def test_closes_connection_after_live_command_failure_async(async_client: AsyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError):
        await async_client.execute_live("exit 47", raise_for_status=True)
    assert_that(connection_is_closed(async_client)).is_true()


def test_closes_connection_after_observer_failure(sync_client: SyncSSHClient) -> None:
    def failing_observer(line: str) -> None:
        raise HookFailureError(line)

    with pytest.raises(HookFailureError):
        sync_client.execute_live("printf 'hook exception\\n'", stdout_callback=failing_observer)
    assert_that(connection_is_closed(sync_client)).is_true()


async def test_closes_connection_after_observer_failure_async(async_client: AsyncSSHClient) -> None:
    def failing_observer(line: str) -> None:
        raise HookFailureError(line)

    with pytest.raises(HookFailureError):
        await async_client.execute_live("printf 'async hook exception\\n'", stdout_callback=failing_observer)
    assert_that(connection_is_closed(async_client)).is_true()


def test_closes_connection_after_timeout(sync_client: SyncSSHClient) -> None:
    with pytest.raises(TimeoutError):
        sync_client.execute("sleep 2", timeout=0.03)
    assert_that(connection_is_closed(sync_client)).is_true()


async def test_closes_connection_after_timeout_async(async_client: AsyncSSHClient) -> None:
    with pytest.raises(TimeoutError):
        await async_client.execute("sleep 2", timeout=0.03)
    assert_that(connection_is_closed(async_client)).is_true()
