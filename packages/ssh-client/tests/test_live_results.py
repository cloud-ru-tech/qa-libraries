from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that
from ssh_client.clients.exceptions import CommandNonZeroExitCodeError

if TYPE_CHECKING:
    from ssh_client import AsyncSSHClient, SyncSSHClient


def test_collects_live_output(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute_live("printf 'first\\nsecond\\n'")
    assert_that(result.stdout_lines).is_equal_to(["first", "second"])


async def test_collects_live_output_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live("printf 'line-a\\nline-b\\n'")
    assert_that(result.stdout_lines).is_equal_to(["line-a", "line-b"])


def test_preserves_partial_lines_across_packets(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute_live("printf 'snow'; sleep 0.05; printf 'flake 雪\\nlast'")
    assert_that(result.stdout_lines).is_equal_to(["snowflake 雪", "last"])


async def test_preserves_partial_lines_across_packets_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live("printf 'first'; sleep 0.05; printf 'last 雨\\nend'")
    assert_that(result.stdout_lines).is_equal_to(["firstlast 雨", "end"])


def test_merges_stderr_into_terminal_output(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute_live("printf 'warning\\n' >&2")
    assert_that((result.stdout_lines, result.stderr_lines)).is_equal_to((["warning"], []))


async def test_collects_stderr_separately_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live("printf 'notice\\n' >&2")
    assert_that((result.stdout_lines, result.stderr_lines)).is_equal_to(([], ["notice"]))


def test_limits_live_command_runtime(sync_client: SyncSSHClient) -> None:
    with pytest.raises(TimeoutError, match="timed out"):
        sync_client.execute_live("sleep 2", timeout=0.05)


async def test_limits_live_command_runtime_async(async_client: AsyncSSHClient) -> None:
    with pytest.raises(TimeoutError):
        await async_client.execute_live("sleep 2", timeout=0.05)


def test_checks_live_command_exit_status(sync_client: SyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError, match="exit code 13"):
        sync_client.execute_live("exit 13", raise_for_status=True)


async def test_checks_live_command_exit_status_async(async_client: AsyncSSHClient) -> None:
    with pytest.raises(CommandNonZeroExitCodeError, match="exit code 31"):
        await async_client.execute_live("exit 31", raise_for_status=True)


def test_calls_live_stdout_observer(sync_client: SyncSSHClient) -> None:
    observed: list[str] = []
    sync_client.execute_live("printf 'alpha\\nbeta\\n'", stdout_callback=observed.append)
    assert_that(observed).is_equal_to(["alpha", "beta"])


async def test_calls_live_stdout_observer_async(async_client: AsyncSSHClient) -> None:
    observed: list[str] = []
    await async_client.execute_live("printf 'north\\nsouth\\n'", stdout_callback=observed.append)
    assert_that(observed).is_equal_to(["north", "south"])


async def test_calls_live_stderr_observer_async(async_client: AsyncSSHClient) -> None:
    observed: list[str] = []
    await async_client.execute_live("printf 'stderr line\\n' >&2", stderr_callback=observed.append)
    assert_that(observed).is_equal_to(["stderr line"])


def test_interrupts_live_stdout(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute_live(
        "printf 'before\\nstop\\n'; sleep 2; printf 'after\\n'",
        interrupt_stdout_callback=lambda line: line == "stop",
    )
    assert_that(result.stdout_lines).is_equal_to(["before", "stop"])


async def test_interrupts_live_stdout_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live(
        "printf 'start\\nabort\\n'; sleep 2; printf 'finish\\n'",
        interrupt_stdout_callback=lambda line: line == "abort",
    )
    assert_that(result.stdout_lines).is_equal_to(["start", "abort"])


async def test_interrupts_live_stderr_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live(
        "printf 'halt\\n' >&2; sleep 2; printf 'late\\n' >&2",
        interrupt_stderr_callback=lambda line: line == "halt",
    )
    assert_that(result.stderr_lines).is_equal_to(["halt"])


def test_preserves_blank_lines(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute_live("printf '\\n\\n'")
    assert_that(result.stdout_lines).is_equal_to(["", ""])


async def test_preserves_blank_lines_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live("printf '\\n\\n'")
    assert_that(result.stdout_lines).is_equal_to(["", ""])


def test_decodes_multibyte_characters_split_across_packets(sync_client: SyncSSHClient) -> None:
    result = sync_client.execute_live("printf '\\351'; sleep 0.05; printf '\\233\\252\\n'")
    assert_that(result.stdout_lines).is_equal_to(["雪"])


async def test_decodes_multibyte_characters_split_across_packets_async(async_client: AsyncSSHClient) -> None:
    result = await async_client.execute_live("printf '\\351'; sleep 0.05; printf '\\233\\252\\n'")
    assert_that(result.stdout_lines).is_equal_to(["雪"])
