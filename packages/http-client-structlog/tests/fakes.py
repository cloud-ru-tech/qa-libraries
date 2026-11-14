from typing import override

from http_client_structlog.event_hooks import REQUEST_EVENT, RESPONSE_EVENT
from structlog.stdlib import BoundLogger


class LogEntry:
    """Record received by the logger."""

    def __init__(self, level: int, event: str, params: dict[str, object]) -> None:
        """Create an instance with the supplied settings."""
        self.level = level
        self.event = event
        self.params = params

    def __repr__(self) -> str:
        return f"LogEntry(level={self.level}, event={self.event!r}, params={self.params!r})"


class FakeStructLogger(BoundLogger):
    """Logger that stores records instead of displaying them."""

    def __init__(self) -> None:
        """Create an instance with the supplied settings."""
        context: dict[str, object] = {}
        super().__init__(logger=None, processors=[], context=context)
        self.entries: list[LogEntry] = []

    @override
    def log(self, level: int, event: str | None = None, *_args: object, **kw: object) -> None:
        self.entries.append(LogEntry(level, event or "", kw))

    @property
    def requests(self) -> list[LogEntry]:
        return [entry for entry in self.entries if entry.event == REQUEST_EVENT]

    @property
    def responses(self) -> list[LogEntry]:
        return [entry for entry in self.entries if entry.event == RESPONSE_EVENT]

    @property
    def request(self) -> LogEntry:
        return self.requests[0]

    @property
    def response(self) -> LogEntry:
        return self.responses[0]
