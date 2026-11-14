import logging
from typing import Protocol, cast

import structlog
from grpc_client_structlog.sink import REQUEST_EVENT, RESPONSE_EVENT, StructLogger
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


class LogMethod(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> None: ...


class CapturingSink:
    """Structlog record sink that stores records instead of printing them.

    Replace the logger created by the structlog factory: the bound logger calls its
    method named for the level, passing record fields as keyword arguments.
    """

    def __init__(self, level: int) -> None:
        """Create an instance with the supplied settings."""
        self.level = level
        self.calls: list[tuple[str, dict[str, object]]] = []

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802 - the stdlib logger defines this method name
        """Check whether records at the specified level reach the output."""
        return level >= self.level

    def __getattr__(self, name: str) -> LogMethod:
        def record(*_args: object, **kwargs: object) -> None:
            self.calls.append((name, kwargs))

        return record


class StructlogRecorder:
    """Bound logger and the records it received."""

    def __init__(self, logger: StructLogger, sink: CapturingSink) -> None:
        """Create an instance with the supplied settings."""
        self.logger = logger
        self._sink = sink

    @property
    def entries(self) -> list[LogEntry]:
        """All records in arrival order."""
        levels = logging.getLevelNamesMapping()
        return [
            LogEntry(
                level=levels[method.upper()],
                event=str(params.get("event", "")),
                params={name: value for name, value in params.items() if name != "event"},
            )
            for method, params in self._sink.calls
        ]

    @property
    def requests(self) -> list[LogEntry]:
        """Records of sent requests."""
        return [entry for entry in self.entries if entry.event == REQUEST_EVENT]

    @property
    def responses(self) -> list[LogEntry]:
        """Records of received responses."""
        return [entry for entry in self.entries if entry.event == RESPONSE_EVENT]

    @property
    def request(self) -> LogEntry:
        """Record of the first sent request."""
        return self.requests[0]

    @property
    def response(self) -> LogEntry:
        """Record of the first received response."""
        return self.responses[0]


def build_stdlib_logger(level: int = logging.DEBUG) -> StructlogRecorder:
    """Build a logger as `structlog.configure(wrapper_class=BoundLogger)` does.

    :param level: minimum level for records to reach output
    :returns: logger with its received records
    """
    sink = CapturingSink(level)
    context: dict[str, object] = {}
    return StructlogRecorder(BoundLogger(sink, [], context), sink)


class ExplodingSink(CapturingSink):
    """Record sink with a broken level check.

    This matches `structlog.stdlib.BoundLogger` with `structlog.PrintLogger`: the bound logger
    delegates the level query to its underlying logger, while `PrintLogger` cannot answer it.
    """

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802, ARG002 - the stdlib logger defines the signature
        """Fail to answer the level query in the same way as `PrintLogger`."""
        message = "'PrintLogger' object has no attribute 'isEnabledFor'"
        raise AttributeError(message)


def build_logger_with_broken_level_check() -> StructlogRecorder:
    """Build a logger whose level check fails but whose writes work.

    :returns: logger with its received records
    """
    sink = ExplodingSink(logging.DEBUG)
    context: dict[str, object] = {}
    return StructlogRecorder(BoundLogger(sink, [], context), sink)


def build_filtering_logger(level: int = logging.DEBUG) -> StructlogRecorder:
    """Build a logger as `wrapper_class=make_filtering_bound_logger(...)` does.

    This logger previously crashed the gRPC client: its level check is named `is_enabled_for`,
    rather than `isEnabledFor`.

    :param level: minimum level for records to reach output
    :returns: logger with its received records
    """
    sink = CapturingSink(level)
    logger = cast(
        "StructLogger",
        structlog.wrap_logger(sink, processors=[], wrapper_class=structlog.make_filtering_bound_logger(level)),
    )
    return StructlogRecorder(logger, sink)
