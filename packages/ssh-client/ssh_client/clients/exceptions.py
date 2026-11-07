from __future__ import annotations

from ssh_client.results import LiveSSHResult, SSHResult


class SSHClientNotDefinedError(Exception):
    """Report an operation without an authenticated transport."""

    def __init__(self, message: str = "SSH client is not defined") -> None:
        """Keep the transport failure reason.

        :param message: Failure description.
        """
        self.message = message
        super().__init__(message)


class CommandNonZeroExitCodeError(Exception):
    """Report a command which returned a failing exit status."""

    @classmethod
    def from_result(cls, result: SSHResult | LiveSSHResult) -> CommandNonZeroExitCodeError:
        """Describe the failed command result.

        :param result: Failed command output and exit status.
        :return: Exception describing the command failure.
        """
        stderr = result.stderr if isinstance(result, SSHResult) else "\n".join(result.stderr_lines)
        return cls(f"Command failed with exit code {result.exit_code}: {stderr}")
