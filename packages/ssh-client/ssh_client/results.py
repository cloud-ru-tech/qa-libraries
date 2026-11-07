from dataclasses import dataclass, field


@dataclass
class SSHResult:
    """Результат выполнения SSH команды."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None

    def __repr__(self) -> str:
        """Return a concise description of the command result."""
        return f"SSHResult(stdout='{self.stdout}', stderr='{self.stderr}', exit_code={self.exit_code})"


@dataclass
class LiveSSHResult:
    """Результат выполнения SSH команды с возможностью получения данных в реальном времени."""

    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    exit_code: int | None = None

    def __repr__(self) -> str:
        """Return a concise description of the command result."""
        return (
            f"LiveSSHResult(stdout_lines={len(self.stdout_lines)}, "
            f"stderr_lines={len(self.stderr_lines)}, exit_code={self.exit_code})"
        )
