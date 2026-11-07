from __future__ import annotations

from typing import TYPE_CHECKING

import asyncssh
import pytest
from assertpy import assert_that
from ssh_client import AsyncSSHClient, options

if TYPE_CHECKING:
    from .support import SSHTestServer


async def test_authenticates_with_password(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute("id -un", raise_for_status=True)
    assert_that(result.stdout).is_equal_to("testuser\n")


async def test_joins_preformatted_command_fragments(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute(["printf", "'%s'", "'async list'"])
    assert_that(result.stdout).is_equal_to("async list")


async def test_preserves_stdout_and_stderr(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute("printf 'output 雨'; printf 'error π' >&2")
    assert_that((result.stdout, result.stderr)).is_equal_to(("output 雨", "error π"))


async def test_runs_complex_shell_commands(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute("printf 'first\\nsecond\\n' | tail -1 | tr a-z A-Z")
    assert_that(result.stdout).is_equal_to("SECOND\n")


async def test_limits_command_runtime(async_client: AsyncSSHClient) -> None:
    with pytest.raises(TimeoutError):
        await async_client.execute("sleep 2", timeout=0.05)


async def test_applies_default_command_timeout(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client(options.with_request_timeout(0.05)) as client:
        with pytest.raises(TimeoutError):
            await client.execute("sleep 2")


async def test_rejects_invalid_password(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client(options.with_password(ssh_server.username, "wrong-value")) as client:
        with pytest.raises(asyncssh.PermissionDenied):
            await client.connect()


async def test_drains_large_stdout_and_stderr_without_deadlock(async_client: AsyncSSHClient) -> None:
    expected_size = 3 * 1024 * 1024
    result = await async_client.execute(f"head -c {expected_size} /dev/zero; head -c {expected_size} /dev/zero >&2")
    assert_that((len(result.stdout), len(result.stderr))).is_equal_to((expected_size, expected_size))
