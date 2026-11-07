from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

import asyncssh
import paramiko
import pytest
from assertpy import assert_that
from ssh_client import AsyncSSHClient, InitSSHClient, SyncSSHClient, options

from .test_decorator_options import OperationCounter

if TYPE_CHECKING:
    from pathlib import Path

    from .support import SSHTestServer


def retrying_command(path: str, succeeds_after: int) -> str:
    quoted = shlex.quote(path)
    return (
        f"n=$(cat {quoted} 2>/dev/null || printf 0); n=$((n+1)); printf '%s' $n > {quoted}; "
        f"printf '%s' $n; [ $n -ge {succeeds_after} ]"
    )


def test_retries_failed_command_until_success(ssh_server: SSHTestServer, remote_file: str) -> None:
    with ssh_server.sync(options.retry_if_command_fails(3, 0)) as client:
        result = client.execute(retrying_command(remote_file, 3))
    assert_that((result.stdout, result.exit_code)).is_equal_to(("3", 0))


async def test_retries_failed_command_until_success_async(ssh_server: SSHTestServer, remote_file: str) -> None:
    async with ssh_server.async_client(options.retry_if_command_fails(3, 0)) as client:
        result = await client.execute(retrying_command(remote_file, 3))
    assert_that((result.stdout, result.exit_code)).is_equal_to(("3", 0))


def test_returns_final_failed_command_result(ssh_server: SSHTestServer, remote_file: str) -> None:
    with ssh_server.sync(options.retry_if_command_fails(2, 0)) as client:
        result = client.execute(retrying_command(remote_file, 9))
    assert_that((result.stdout, result.exit_code)).is_equal_to(("2", 1))


async def test_returns_final_failed_command_result_async(ssh_server: SSHTestServer, remote_file: str) -> None:
    async with ssh_server.async_client(options.retry_if_command_fails(2, 0)) as client:
        result = await client.execute(retrying_command(remote_file, 7))
    assert_that((result.stdout, result.exit_code)).is_equal_to(("2", 1))


def test_retries_connection_errors(ssh_server: SSHTestServer, unused_tcp_port: int) -> None:
    counter = OperationCounter()
    with (
        SyncSSHClient(
            ssh_server.host,
            unused_tcp_port,
            options.with_password(ssh_server.username, ssh_server.password),
            options.with_connect_decorators(counter),
            options.with_connection_timeout(0.1),
            options.retry_if_connection_fails(3, 0, reraise_exception=True),
        ) as client,
        pytest.raises(paramiko.ssh_exception.NoValidConnectionsError),
    ):
        client.connect()
    assert_that(counter.events).is_length(3)


async def test_retries_connection_errors_async(ssh_server: SSHTestServer, unused_tcp_port: int) -> None:
    counter = OperationCounter()
    async with AsyncSSHClient(
        ssh_server.host,
        unused_tcp_port,
        options.with_password(ssh_server.username, ssh_server.password),
        options.with_connect_decorators(counter),
        options.with_connection_timeout(0.1),
        options.retry_if_connection_fails(3, 0, reraise_exception=True),
    ) as client:
        with pytest.raises(ConnectionRefusedError):
            await client.connect()
    assert_that(counter.events).is_length(3)


def test_rejects_unknown_server_key(ssh_server: SSHTestServer, tmp_path: Path) -> None:
    unknown = tmp_path / "known_hosts"
    unknown.touch()
    with (
        ssh_server.sync(options.with_known_hosts(str(unknown))) as client,
        pytest.raises(paramiko.SSHException, match="not found in known_hosts"),
    ):
        client.connect()


async def test_rejects_unknown_server_key_async(ssh_server: SSHTestServer, tmp_path: Path) -> None:
    unknown = tmp_path / "known_hosts"
    unknown.touch()
    async with ssh_server.async_client(options.with_known_hosts(str(unknown))) as client:
        with pytest.raises(asyncssh.HostKeyNotVerifiable, match="not trusted"):
            await client.connect()


def test_rejects_changed_server_key(ssh_server: SSHTestServer, tmp_path: Path) -> None:
    changed = _wrong_host_key(ssh_server, tmp_path)
    with ssh_server.sync(options.with_known_hosts(str(changed))) as client, pytest.raises(paramiko.BadHostKeyException):
        client.connect()


async def test_rejects_changed_server_key_async(ssh_server: SSHTestServer, tmp_path: Path) -> None:
    changed = _wrong_host_key(ssh_server, tmp_path)
    async with ssh_server.async_client(options.with_known_hosts(str(changed))) as client:
        with pytest.raises(asyncssh.HostKeyNotVerifiable, match="not trusted"):
            await client.connect()


def _wrong_host_key(server: SSHTestServer, directory: Path) -> Path:
    changed = directory / "changed_known_hosts"
    key = paramiko.RSAKey.generate(3072)
    changed.write_text(f"[{server.host}]:{server.port} {key.get_name()} {key.get_base64()}\n", encoding="utf-8")
    return changed


def test_custom_option_receives_actual_client(ssh_server: SSHTestServer) -> None:
    observed: list[InitSSHClient] = []

    def custom_option(client: InitSSHClient) -> None:
        observed.append(client)
        client.add_connect_decorator(OperationCounter())

    with ssh_server.sync(custom_option) as client:
        client.execute("true")
    assert_that(observed).contains_only(client)


async def test_custom_option_receives_actual_client_async(ssh_server: SSHTestServer) -> None:
    observed: list[InitSSHClient] = []

    def custom_option(client: InitSSHClient) -> None:
        observed.append(client)
        client.add_execute_decorator(OperationCounter())

    async with ssh_server.async_client(custom_option) as client:
        await client.execute("true")
    assert_that(observed).contains_only(client)


def test_uses_standard_known_hosts(
    ssh_server: SSHTestServer, standard_ssh_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(standard_ssh_home))
    with SyncSSHClient(
        ssh_server.host,
        ssh_server.port,
        options.with_password(ssh_server.username, ssh_server.password),
    ) as client:
        result = client.execute("printf 'default trust'", raise_for_status=True)
    assert_that(result.stdout).is_equal_to("default trust")


async def test_uses_standard_known_hosts_async(
    ssh_server: SSHTestServer,
    standard_ssh_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(standard_ssh_home))
    async with AsyncSSHClient(
        ssh_server.host,
        ssh_server.port,
        options.with_password(ssh_server.username, ssh_server.password),
    ) as client:
        result = await client.execute("printf 'async default trust'", raise_for_status=True)
    assert_that(result.stdout).is_equal_to("async default trust")


def test_rejects_unknown_server_key_by_default(
    ssh_server: SSHTestServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with (
        SyncSSHClient(
            ssh_server.host,
            ssh_server.port,
            options.with_password(ssh_server.username, ssh_server.password),
        ) as client,
        pytest.raises(paramiko.SSHException, match="not found in known_hosts"),
    ):
        client.connect()


async def test_rejects_unknown_server_key_by_default_async(
    ssh_server: SSHTestServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    async with AsyncSSHClient(
        ssh_server.host,
        ssh_server.port,
        options.with_password(ssh_server.username, ssh_server.password),
    ) as client:
        with pytest.raises(asyncssh.HostKeyNotVerifiable, match="not trusted"):
            await client.connect()
