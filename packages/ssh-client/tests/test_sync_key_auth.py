from __future__ import annotations

from typing import TYPE_CHECKING

from assertpy import assert_that
from ssh_client import options

if TYPE_CHECKING:
    from .support import SSHTestServer


def test_authenticates_with_private_key(ssh_server: SSHTestServer) -> None:
    with ssh_server.sync(options.with_private_key(ssh_server.username, ssh_server.private_key)) as client:
        result = client.execute("id -un", raise_for_status=True)
    assert_that(result.stdout).is_equal_to(ssh_server.username + "\n")


def test_executes_shell_pipeline_with_private_key(ssh_server: SSHTestServer) -> None:
    with ssh_server.sync(options.with_private_key(ssh_server.username, ssh_server.private_key)) as client:
        result = client.execute("printf 'key\\nauth\\n' | wc -l")
    assert_that(result.stdout.strip()).is_equal_to("2")
