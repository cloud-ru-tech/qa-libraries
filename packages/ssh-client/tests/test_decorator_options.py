from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from assertpy import assert_that
from ssh_client import options

if TYPE_CHECKING:
    from collections.abc import Callable

    from .support import SSHTestServer


@dataclass
class OperationCounter:
    label: str = "operation"
    events: list[str] = field(default_factory=list)

    def __call__[T](self, operation: Callable[[], T]) -> Callable[[], T]:
        def wrapped() -> T:
            self.events.append(self.label)
            return operation()

        return wrapped


def test_wraps_connection_operation(ssh_server: SSHTestServer) -> None:
    counter = OperationCounter()
    with ssh_server.sync(options.with_connect_decorators(counter)) as client:
        client.execute("true")
    assert_that(counter.events).is_equal_to(["operation"])


def test_wraps_command_operation(ssh_server: SSHTestServer) -> None:
    counter = OperationCounter("command")
    with ssh_server.sync(options.with_execute_decorators(counter)) as client:
        client.execute("printf 'decorated'")
    assert_that(counter.events).is_equal_to(["command"])


async def test_wraps_async_connection_operation(ssh_server: SSHTestServer) -> None:
    counter = OperationCounter("async connection")
    async with ssh_server.async_client(options.with_connect_decorators(counter)) as client:
        await client.execute("true")
    assert_that(counter.events).is_equal_to(["async connection"])


async def test_wraps_async_command_operation(ssh_server: SSHTestServer) -> None:
    counter = OperationCounter("async command")
    async with ssh_server.async_client(options.with_execute_decorators(counter)) as client:
        await client.execute("printf 'async decorated'")
    assert_that(counter.events).is_equal_to(["async command"])


def test_applies_multiple_decorators_in_registration_order(ssh_server: SSHTestServer) -> None:
    events: list[str] = []
    with ssh_server.sync(
        options.with_execute_decorators(
            OperationCounter("outer", events),
            OperationCounter("inner", events),
        )
    ) as client:
        client.execute("true")
    assert_that(events).is_equal_to(["outer", "inner"])


async def test_applies_async_decorators_in_registration_order(ssh_server: SSHTestServer) -> None:
    events: list[str] = []
    async with ssh_server.async_client(
        options.with_execute_decorators(
            OperationCounter("async outer", events),
            OperationCounter("async inner", events),
        )
    ) as client:
        await client.execute("true")
    assert_that(events).is_equal_to(["async outer", "async inner"])
