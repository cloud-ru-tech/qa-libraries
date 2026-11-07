from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from assertpy import assert_that
from ssh_client import options

if TYPE_CHECKING:
    from io import StringIO
    from logging import Logger

    from .support import SSHTestServer


@dataclass
class StructuredLog:
    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **values: object) -> None:
        self.entries.append((event, values))


def test_logs_requests_and_responses(ssh_server: SSHTestServer, string_logger: tuple[Logger, StringIO]) -> None:
    logger, output = string_logger
    with ssh_server.sync(options.with_logger(logger)) as client:
        client.execute("printf 'logged output'")
    assert_that(output.getvalue()).contains("SSH request:", "SSH response:", "logged output", "exit_code=0")


async def test_logs_requests_and_responses_async(
    ssh_server: SSHTestServer,
    string_logger: tuple[Logger, StringIO],
) -> None:
    logger, output = string_logger
    async with ssh_server.async_client(options.with_logger(logger)) as client:
        await client.execute("printf 'async logged output'")
    assert_that(output.getvalue()).contains("SSH request:", "SSH response:", "async logged output")


def test_masks_literal_secrets(ssh_server: SSHTestServer, string_logger: tuple[Logger, StringIO]) -> None:
    logger, output = string_logger
    with ssh_server.sync(options.with_logger(logger, ["private-fragment"])) as client:
        client.execute("printf 'private-fragment'; printf 'private-fragment' >&2")
    assert_that(output.getvalue()).does_not_contain("private-fragment").contains("****")


def test_masks_regular_expression_matches(ssh_server: SSHTestServer, string_logger: tuple[Logger, StringIO]) -> None:
    logger, output = string_logger
    with ssh_server.sync(options.with_logger(logger, [re.compile(r"secret-\d+")])) as client:
        client.execute("printf 'secret-1357'")
    assert_that(output.getvalue()).does_not_contain("secret-1357").contains("****")


def test_logs_live_results(ssh_server: SSHTestServer, string_logger: tuple[Logger, StringIO]) -> None:
    logger, output = string_logger
    with ssh_server.sync(options.with_logger(logger)) as client:
        client.execute_live("printf 'streamed log\\n'")
    assert_that(output.getvalue()).contains("SSH response:", "streamed log")


async def test_logs_live_results_async(ssh_server: SSHTestServer, string_logger: tuple[Logger, StringIO]) -> None:
    logger, output = string_logger
    async with ssh_server.async_client(options.with_logger(logger)) as client:
        await client.execute_live("printf 'live error\\n' >&2")
    assert_that(output.getvalue()).contains("SSH response:", "live error")


def test_logs_structured_requests(ssh_server: SSHTestServer) -> None:
    logger = StructuredLog()
    with ssh_server.sync(options.with_structlogger(logger)) as client:
        client.execute("printf 'structured'")
    assert_that(logger.entries[0][1]).contains_entry(host=ssh_server.host, username=ssh_server.username)


def test_logs_structured_responses(ssh_server: SSHTestServer) -> None:
    logger = StructuredLog()
    with ssh_server.sync(options.with_structlogger(logger)) as client:
        client.execute("printf 'response'")
    assert_that(logger.entries[1][1]).contains_entry(stdout="response", stderr="", exit_code=0)


def test_masks_structured_secrets(ssh_server: SSHTestServer) -> None:
    logger = StructuredLog()
    with ssh_server.sync(options.with_structlogger(logger, ["structured-secret"])) as client:
        client.execute("printf 'structured-secret'")
    assert_that(str(logger.entries)).does_not_contain("structured-secret").contains("****")


async def test_masks_structured_secrets_async(ssh_server: SSHTestServer) -> None:
    logger = StructuredLog()
    async with ssh_server.async_client(options.with_structlogger(logger, [re.compile(r"credential-\d+")])) as client:
        await client.execute("printf 'credential-8246'")
    assert_that(str(logger.entries)).does_not_contain("credential-8246").contains("****")
