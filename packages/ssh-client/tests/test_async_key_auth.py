from __future__ import annotations

from typing import TYPE_CHECKING

from assertpy import assert_that
from ssh_client import options

if TYPE_CHECKING:
    from .support import SSHTestServer


async def test_authenticates_with_private_key(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client(options.with_private_key(ssh_server.username, ssh_server.private_key)) as client:
        result = await client.execute("id -un", raise_for_status=True)
    assert_that(result.stdout).is_equal_to(ssh_server.username + "\n")


async def test_executes_shell_pipeline_with_private_key(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client(options.with_private_key(ssh_server.username, ssh_server.private_key)) as client:
        result = await client.execute("printf 'private\\nkey\\nauth\\n' | wc -l")
    assert_that(result.stdout.strip()).is_equal_to("3")
