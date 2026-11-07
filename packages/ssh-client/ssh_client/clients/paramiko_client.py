from __future__ import annotations

import time
from codecs import getincrementaldecoder
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Unpack

import paramiko

from ssh_client.client import BaseSSHClient
from ssh_client.config import ExecutionSettings
from ssh_client.results import LiveSSHResult, SSHResult

from .exceptions import CommandNonZeroExitCodeError, SSHClientNotDefinedError

if TYPE_CHECKING:
    from codecs import IncrementalDecoder

    from ssh_client.types import ExecuteOptions, LiveExecuteOptions, OutputCallback


@dataclass
class _LiveOutput:
    settings: ExecutionSettings
    callbacks: tuple[OutputCallback | None, ...]
    lines: list[str] = field(default_factory=list)
    pending: str = ""
    decoder: IncrementalDecoder = field(default_factory=getincrementaldecoder("utf-8"))

    def receive(self, data: bytes, *, final: bool = False) -> bool:
        self.pending += self.decoder.decode(data, final=final)
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if self._line(line.removesuffix("\r")):
                return True
        return bool(final and self.pending and self._line(self.pending))

    def _line(self, line: str) -> bool:
        self.lines.append(line)
        for callback in self.callbacks:
            if callback is not None:
                callback(line)
        interrupt = self.settings.interrupt_stdout_callback
        return interrupt is not None and interrupt(line)


class SyncSSHClient(BaseSSHClient[paramiko.SSHClient]):
    """Run SSH commands through Paramiko with trusted server keys."""

    def connect(self) -> None:
        """Open a connection after checking the server host key."""
        if self._connected:
            return
        operation = self._decorate(self._connect_attempt, self._connect_decorators)
        if self.connection_retry is None:
            operation()
        else:
            self.connection_retry.connect(operation)

    def execute(self, command: str | list[str], **options: Unpack[ExecuteOptions]) -> SSHResult:
        """Execute a command and close its connection.

        :param command: Shell command or preformatted shell fragments.
        :param options: Timeout and keyword-only status-check settings.
        :return: Captured output and exit status.
        """
        settings = ExecutionSettings(**options)
        text = " ".join(command) if isinstance(command, list) else command
        try:
            self.connect()
            self._request(text)

            def execute() -> SSHResult:
                return self._execute_command(text, settings)

            operation = self._decorate(execute, self._execute_decorators)
            result = operation() if self.command_retry is None else self.command_retry.execute(operation)
            self._response(text, result)
            if settings.raise_for_status and result.exit_code != 0:
                raise CommandNonZeroExitCodeError.from_result(result)
            return result
        finally:
            self.close()

    def execute_live(self, command: str | list[str], **options: Unpack[LiveExecuteOptions]) -> LiveSSHResult:
        """Stream command lines through callbacks and close the connection.

        Paramiko uses a terminal so that interrupting output also stops the remote process;
        stderr is therefore merged into stdout.

        :param command: Shell command or preformatted shell fragments.
        :param options: Timeout, status checking, stdout callbacks and interrupt callback.
        :return: Collected output lines and exit status.
        """
        settings = ExecutionSettings(**options)
        text = " ".join(command) if isinstance(command, list) else command
        try:
            self.connect()
            self._request(text)
            result = self._execute_live_command(text, settings)
            self._response(text, result)
            if settings.raise_for_status and result.exit_code != 0:
                raise CommandNonZeroExitCodeError.from_result(result)
            return result
        finally:
            self.close()

    def _connect_attempt(self) -> None:
        self.close()
        if not self.username:
            message = "Username must be set by authentication options (with_password or with_private_key)"
            raise ValueError(message)
        self._client = paramiko.SSHClient()
        if self.known_hosts is None:
            self._client.load_system_host_keys()
        else:
            self._client.load_host_keys(self.known_hosts)
        try:
            self._client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                key_filename=self.private_key_path,
                timeout=self.connection_timeout if self.connection_timeout is not None else self.timeout,
                allow_agent=self.password is None and self.private_key_path is None,
                look_for_keys=self.password is None and self.private_key_path is None,
            )
        except BaseException:
            self.close()
            raise
        self._connected = True

    def _require_client(self) -> paramiko.SSHClient:
        if self._client is None or not self._connected:
            raise SSHClientNotDefinedError
        return self._client

    def _execute_command(self, command: str, settings: ExecutionSettings) -> SSHResult:
        transport = self._require_client()
        stdin, stdout, stderr = transport.exec_command(command, timeout=settings.timeout or self.timeout)
        stdin.close()
        try:
            return self._collect_output(stdout.channel, settings)
        finally:
            stdout.close()
            stderr.close()

    def _collect_output(self, channel: paramiko.Channel, settings: ExecutionSettings) -> SSHResult:
        output = bytearray()
        errors = bytearray()
        deadline = time.monotonic() + (self.timeout if settings.timeout is None else settings.timeout)
        while True:
            if channel.recv_ready():
                output.extend(channel.recv(65536))
            if channel.recv_stderr_ready():
                errors.extend(channel.recv_stderr(65536))
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                return SSHResult(output.decode("utf-8"), errors.decode("utf-8"), channel.recv_exit_status())
            self._wait_for_output(deadline)

    def _execute_live_command(self, command: str, settings: ExecutionSettings) -> LiveSSHResult:
        stdin, stdout, stderr = self._require_client().exec_command(
            command,
            timeout=settings.timeout or self.timeout,
            get_pty=True,
        )
        stdin.close()
        output = _LiveOutput(settings, (settings.stdout_callback, self.live_stdout_callback))
        deadline = time.monotonic() + (self.timeout if settings.timeout is None else settings.timeout)
        try:
            while True:
                if stdout.channel.recv_ready() and output.receive(stdout.channel.recv(65536)):
                    stdout.channel.send(b"\x03")
                    stdout.channel.close()
                    return LiveSSHResult(output.lines, [], -1)
                if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
                    output.receive(b"", final=True)
                    return LiveSSHResult(output.lines, [], stdout.channel.recv_exit_status())
                self._wait_for_output(deadline)
        finally:
            stdout.close()
            stderr.close()

    @staticmethod
    def _wait_for_output(deadline: float) -> None:
        if time.monotonic() >= deadline:
            message = "SSH command timed out"
            raise TimeoutError(message)
        time.sleep(0.01)
