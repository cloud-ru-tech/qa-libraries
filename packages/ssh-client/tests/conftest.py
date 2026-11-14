from __future__ import annotations

import logging
import shlex
import socket
import time
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import paramiko
import pytest

from .support import SSHTestServer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from pytest_docker.plugin import Services
    from ssh_client import AsyncSSHClient, SyncSSHClient


class SSHServerStartupError(RuntimeError):
    pass


@pytest.fixture(scope="session")
def server_key(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, paramiko.RSAKey]:
    directory = tmp_path_factory.mktemp("ssh-host-keys")
    key = paramiko.RSAKey.generate(3072)
    key.write_private_key_file(str(directory / "ssh_host_rsa_key"))
    return directory, key


@pytest.fixture(scope="session")
def client_key() -> paramiko.RSAKey:
    return paramiko.RSAKey.generate(3072)


@pytest.fixture(scope="session")
def authorized_keys(client_key: paramiko.RSAKey, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("ssh-authorized-keys")
    # sshd reads authorized_keys as testuser, while mktemp restricts the directory to its owner.
    directory.chmod(0o755)
    keys = directory / "authorized_keys"
    keys.write_text(f"{client_key.get_name()} {client_key.get_base64()}\n", encoding="utf-8")
    keys.chmod(0o644)
    return directory


@pytest.fixture(scope="session")
def docker_compose_file(
    server_key: tuple[Path, paramiko.RSAKey],
    authorized_keys: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> list[str]:
    host_keys, _ = server_key
    override = tmp_path_factory.mktemp("ssh-compose") / "keys.yml"
    override.write_text(
        "services:\n"
        "  ssh-test-server:\n"
        "    volumes:\n"
        f"      - '{host_keys}:/etc/ssh/keys:ro'\n"
        f"      - '{authorized_keys}:/etc/ssh/authorized:ro'\n",
        encoding="utf-8",
    )
    return [str(Path(__file__).with_name("docker-compose.yml")), str(override)]


@pytest.fixture(scope="session")
def ssh_server(
    docker_services: Services,
    server_key: tuple[Path, paramiko.RSAKey],
    client_key: paramiko.RSAKey,
    tmp_path_factory: pytest.TempPathFactory,
) -> SSHTestServer:
    port = docker_services.port_for("ssh-test-server", 22)
    _wait_until_responsive(port)
    directory = tmp_path_factory.mktemp("ssh-client-keys")
    _, key = server_key
    known_hosts = directory / "known_hosts"
    known_hosts.write_text(f"[127.0.0.1]:{port} {key.get_name()} {key.get_base64()}\n", encoding="utf-8")
    private_key = directory / "client_key"
    client_key.write_private_key_file(str(private_key))
    account = ("testuser", "testpass")
    return SSHTestServer("127.0.0.1", port, account[0], account[1], str(private_key), str(known_hosts))


def _wait_until_responsive(port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise SSHServerStartupError


@pytest.fixture()
def sync_client(ssh_server: SSHTestServer) -> Iterator[SyncSSHClient]:
    with ssh_server.sync() as client:
        yield client


@pytest.fixture()
async def async_client(ssh_server: SSHTestServer) -> AsyncIterator[AsyncSSHClient]:
    async with ssh_server.async_client() as client:
        yield client


@pytest.fixture()
def string_logger() -> Iterator[tuple[logging.Logger, StringIO]]:
    logger = logging.getLogger("ssh-test")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    with StringIO() as stream:
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        try:
            yield logger, stream
        finally:
            logger.removeHandler(handler)
            handler.close()


@pytest.fixture()
def remote_file(ssh_server: SSHTestServer) -> Iterator[str]:
    path = f"/home/{ssh_server.username}/qa-file-{uuid4().hex}"
    try:
        yield path
    finally:
        with ssh_server.sync() as cleanup:
            cleanup.execute(f"rm -f {shlex.quote(path)}", raise_for_status=True)


@pytest.fixture()
def standard_ssh_home(ssh_server: SSHTestServer, tmp_path: Path) -> Path:
    directory = tmp_path / ".ssh"
    directory.mkdir()
    (directory / "known_hosts").write_bytes(Path(ssh_server.known_hosts).read_bytes())
    return tmp_path
