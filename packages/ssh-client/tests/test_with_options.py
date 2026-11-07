from __future__ import annotations

from typing import TYPE_CHECKING

from assertpy import assert_that
from ssh_client import options

from .support import connection_is_closed
from .test_decorator_options import OperationCounter

if TYPE_CHECKING:
    from .support import SSHTestServer


def test_temporary_timeout_does_not_change_original(ssh_server: SSHTestServer) -> None:
    with ssh_server.sync(options.with_request_timeout(3)) as original:
        with original.with_options(options.with_request_timeout(0.15)) as temporary:
            temporary.execute("true")
        result = original.execute("sleep 0.3; printf 'original'")
    assert_that(result.stdout).is_equal_to("original")


async def test_temporary_timeout_does_not_change_original_async(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client(options.with_request_timeout(3)) as original:
        async with original.with_options(options.with_request_timeout(0.15)) as temporary:
            await temporary.execute("true")
        result = await original.execute("sleep 0.3; printf 'unchanged'")
    assert_that(result.stdout).is_equal_to("unchanged")


def test_clones_connected_client_without_closing_original(ssh_server: SSHTestServer) -> None:
    with ssh_server.sync() as original:
        original.connect()
        with original.with_options() as temporary:
            temporary.execute("printf 'separate'")
        closed = connection_is_closed(original)
    assert_that(closed).is_false()


async def test_clones_connected_client_without_closing_original_async(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client() as original:
        await original.connect()
        async with original.with_options() as temporary:
            await temporary.execute("printf 'independent'")
        closed = connection_is_closed(original)
    assert_that(closed).is_false()


def test_temporary_decorator_does_not_leak_into_original(ssh_server: SSHTestServer) -> None:
    counter = OperationCounter()
    with ssh_server.sync() as original:
        with original.with_options(options.with_execute_decorators(counter)) as temporary:
            temporary.execute("true")
        original.execute("true")
    assert_that(counter.events).is_equal_to(["operation"])


async def test_temporary_decorator_does_not_leak_into_original_async(ssh_server: SSHTestServer) -> None:
    counter = OperationCounter("isolated")
    async with ssh_server.async_client() as original:
        async with original.with_options(options.with_execute_decorators(counter)) as temporary:
            await temporary.execute("true")
        await original.execute("true")
    assert_that(counter.events).is_equal_to(["isolated"])


def test_uses_default_live_callback(ssh_server: SSHTestServer) -> None:
    observed: list[str] = []
    with ssh_server.sync(options.with_live_execute_callback(observed.append)) as client:
        client.execute_live("printf 'configured callback\\n'")
    assert_that(observed).is_equal_to(["configured callback"])


async def test_uses_default_live_callbacks_async(ssh_server: SSHTestServer) -> None:
    observed: list[str] = []
    async with ssh_server.async_client(options.with_live_execute_callback(stderr_callback=observed.append)) as client:
        await client.execute_live("printf 'configured error\\n' >&2")
    assert_that(observed).is_equal_to(["configured error"])


def test_preserves_fluent_command_api(ssh_server: SSHTestServer) -> None:
    with ssh_server.sync() as client:
        result = client.with_options(options.with_request_timeout(2)).execute("printf 'fluent'")
    assert_that(result.stdout).is_equal_to("fluent")


async def test_preserves_fluent_command_api_async(ssh_server: SSHTestServer) -> None:
    async with ssh_server.async_client() as client:
        result = await client.with_options(options.with_request_timeout(2)).execute("printf 'async fluent'")
    assert_that(result.stdout).is_equal_to("async fluent")
