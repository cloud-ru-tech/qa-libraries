from __future__ import annotations

from typing import TYPE_CHECKING

import paramiko
import pytest
from assertpy import assert_that
from ssh_client import SyncSSHClient, options

if TYPE_CHECKING:
    from .support import SSHTestServer


def test_authenticates_with_password(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute("id -un", raise_for_status=True)
    assert_that(result.stdout).is_equal_to("testuser\n")


def test_joins_preformatted_command_fragments(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute(["printf", "'%s'", "'list argument'"])
    assert_that(result.stdout).is_equal_to("list argument")


def test_preserves_stdout_and_stderr(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute("printf 'out 雪'; printf 'err λ' >&2")
    assert_that((result.stdout, result.stderr)).is_equal_to(("out 雪", "err λ"))


def test_runs_complex_shell_commands(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute("printf 'alpha\\nbeta\\ngamma\\n' | grep 'beta' | tr a-z A-Z")
    assert_that(result.stdout).is_equal_to("BETA\n")


def test_limits_command_runtime(sync_client: SyncSSHClient) -> None:
    with pytest.raises(TimeoutError, match="timed out"):
        sync_client.execute("sleep 2", timeout=0.05)


def test_applies_default_command_timeout(ssh_server: SSHTestServer) -> None:
    with ssh_server.sync(options.with_request_timeout(0.05)) as client, pytest.raises(TimeoutError, match="timed out"):
        client.execute("sleep 2")


def test_rejects_invalid_password(ssh_server: SSHTestServer) -> None:
    with (
        ssh_server.sync(options.with_password(ssh_server.username, "incorrect")) as client,
        pytest.raises(paramiko.AuthenticationException),
    ):
        client.connect()


def test_drains_large_stdout_and_stderr_without_deadlock(sync_client: SyncSSHClient) -> None:
    expected_size = 3 * 1024 * 1024
    result = sync_client.execute(f"head -c {expected_size} /dev/zero; head -c {expected_size} /dev/zero >&2")
    assert_that((len(result.stdout), len(result.stderr))).is_equal_to((expected_size, expected_size))
