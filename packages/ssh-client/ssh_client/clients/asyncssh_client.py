from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Unpack, cast

import asyncssh

from ssh_client.client import BaseAsyncSSHClient
from ssh_client.config import ExecutionSettings
from ssh_client.results import LiveSSHResult, SSHResult

from .exceptions import CommandNonZeroExitCodeError, SSHClientNotDefinedError

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from ssh_client.types import AsyncOperation, ExecuteOptions, InterruptCallback, LiveExecuteOptions, OutputCallback


@dataclass
class _StreamReader:
    process: asyncssh.SSHClientProcess[str]
    lines: list[str]
    callbacks: tuple[OutputCallback | None, ...]
    interrupt: InterruptCallback | None

    async def read(self, stream: asyncssh.SSHReader[str]) -> None:
        async for raw in stream:
            if not raw:
                continue
            line = raw.removesuffix("\n").removesuffix("\r")
            self.lines.append(line)
            for callback in self.callbacks:
                if callback is not None:
                    callback(line)
            if self.interrupt is not None and self.interrupt(line):
                self.process.send_signal("INT")
                return


class AsyncSSHClient(BaseAsyncSSHClient[asyncssh.SSHClientConnection]):
    """Run asynchronous SSH commands with trusted server keys."""

    async def connect(self) -> None:
        """Open a connection after checking the server host key."""
        if self._connected:
            return
        operation: AsyncOperation[None] = self._connect_attempt
        operation = self._decorate(operation, self._connect_decorators)
        if self.connection_retry is None:
            await operation()
        else:
            await self.connection_retry.connect_async(operation)

    async def execute(self, command: str | list[str], **options: Unpack[ExecuteOptions]) -> SSHResult:
        """Execute a command and wait for connection cleanup.

        :param command: Shell command or preformatted shell fragments.
        :param options: Timeout and keyword-only status-check settings.
        :return: Captured output and exit status.
        """
        settings = ExecutionSettings(**options)
        text = " ".join(command) if isinstance(command, list) else command
        try:
            await self.connect()
            self._request(text)

            async def execute() -> SSHResult:
                return await self._execute_command(text, settings)

            operation: AsyncOperation[SSHResult] = execute
            operation = self._decorate(operation, self._execute_decorators)
            result = (
                await operation() if self.command_retry is None else await self.command_retry.execute_async(operation)
            )
            self._response(text, result)
            if settings.raise_for_status and result.exit_code != 0:
                raise CommandNonZeroExitCodeError.from_result(result)
            return result
        finally:
            await self.aclose()

    async def execute_live(self, command: str | list[str], **options: Unpack[LiveExecuteOptions]) -> LiveSSHResult:
        """Stream stdout and stderr concurrently and release the connection.

        :param command: Shell command or preformatted shell fragments.
        :param options: Timeout, status checking, output callbacks and interrupt callbacks.
        :return: Collected output lines and exit status.
        """
        settings = ExecutionSettings(**options)
        text = " ".join(command) if isinstance(command, list) else command
        try:
            await self.connect()
            self._request(text)
            result = await self._execute_live_command(text, settings)
            self._response(text, result)
            if settings.raise_for_status and result.exit_code != 0:
                raise CommandNonZeroExitCodeError.from_result(result)
            return result
        finally:
            await self.aclose()

    async def _connect_attempt(self) -> None:
        await self.aclose()
        if not self.username:
            message = "Username must be set by authentication options (with_password or with_private_key)"
            raise ValueError(message)
        client_keys: list[str] | tuple[()] = [self.private_key_path] if self.private_key_path is not None else ()
        self._client = await asyncssh.connect(
            self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            client_keys=client_keys,
            known_hosts=self.known_hosts if self.known_hosts is not None else (),
            connect_timeout=self.connection_timeout if self.connection_timeout is not None else self.timeout,
        )
        self._connected = True

    def _require_client(self) -> asyncssh.SSHClientConnection:
        if self._client is None or not self._connected:
            raise SSHClientNotDefinedError
        return self._client

    async def _execute_command(self, command: str, settings: ExecutionSettings) -> SSHResult:
        async with asyncio.timeout(self.timeout if settings.timeout is None else settings.timeout):
            result = await self._require_client().run(command, encoding="utf-8")
        output = result.stdout.decode("utf-8") if isinstance(result.stdout, bytes) else result.stdout
        errors = result.stderr.decode("utf-8") if isinstance(result.stderr, bytes) else result.stderr
        return SSHResult(output or "", errors or "", result.returncode)

    async def _execute_live_command(self, command: str, settings: ExecutionSettings) -> LiveSSHResult:
        async with cast(
            "AbstractAsyncContextManager[asyncssh.SSHClientProcess[str]]",
            self._require_client().create_process(command, encoding="utf-8"),
        ) as process:
            output: list[str] = []
            errors: list[str] = []
            stdout = _StreamReader(
                process,
                output,
                (settings.stdout_callback, self.live_stdout_callback),
                settings.interrupt_stdout_callback,
            )
            stderr = _StreamReader(
                process,
                errors,
                (settings.stderr_callback, self.live_stderr_callback),
                settings.interrupt_stderr_callback,
            )
            async with asyncio.timeout(self.timeout if settings.timeout is None else settings.timeout):
                await asyncio.gather(stdout.read(process.stdout), stderr.read(process.stderr))
                await process.wait()
            return LiveSSHResult(output, errors, process.returncode)
