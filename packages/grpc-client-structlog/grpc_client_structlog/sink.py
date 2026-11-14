import logging

import grpc
from grpc_client import RequestRecord, ResponseRecord
from grpc_client.utils.logutils import LogFormat
from structlog.stdlib import BoundLogger
from structlog.typing import FilteringBoundLogger

from .parser import parse_error, parse_request, parse_response, parse_stream_response

# Structlog bound logger: stdlib-based or a class from `make_filtering_bound_logger`.
# The second does not fit the first: its level check methods have different names.
StructLogger = BoundLogger | FilteringBoundLogger

# Sent request event.
REQUEST_EVENT = "grpc request sent"

# Received response event: success, failure, or stream completion.
RESPONSE_EVENT = "grpc response received"

# Levels supported by structlog.
#
# A stdlib logger accepts any number, while a structlog bound logger selects a method by level name,
# and only these five levels have names. A stdlib logger would write an intermediate value such as 15,
# but structlog raises `KeyError`.
SUPPORTED_LOG_LEVELS = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)


class StructlogSink:
    """Sink that writes gRPC call records to structlog as separate fields."""

    def __init__(self, logger: StructLogger, log_format: LogFormat | None = None) -> None:
        """Initialize the object.

        :param logger: structured logger used for requests and responses
        :param log_format: log formatting rules, defaults to shared configuration
        """
        self._logger = logger
        self._format = log_format if log_format is not None else LogFormat.from_config()

    def is_enabled_for(self, level: int) -> bool:
        """Check whether the logger writes records at the specified level.

        The check may fail: users set the bound logger class in `structlog.configure`,
        and `structlog.stdlib.BoundLogger`, for example, delegates the query to its underlying logger,
        while `structlog.PrintLogger` cannot answer it. Treat such a logger as enabled:
        silently losing records is worse than building an extra one, and breaking the
        call itself over this query is even worse.

        :param level: record level
        :returns: True if a record at this level reaches output
        """
        try:
            return self._logger.is_enabled_for(level)
        except Exception:  # noqa: BLE001 - a broken check must not break the call
            return True

    def write_request(self, level: int, record: RequestRecord) -> None:
        """Log a sent request."""
        self._write(level, REQUEST_EVENT, parse_request(record, self._format))

    def write_response(self, level: int, record: ResponseRecord) -> None:
        """Log a completed call."""
        self._write(level, RESPONSE_EVENT, self._response_properties(record))

    def _response_properties(self, record: ResponseRecord) -> dict[str, object]:
        """Build log fields suitable for the call outcome."""
        if record.status_code is not grpc.StatusCode.OK:
            return parse_error(record, self._format)
        if record.messages_count is not None:
            return parse_stream_response(record, self._format)
        return parse_response(record, self._format)

    def _write(self, level: int, event: str, properties: dict[str, object]) -> None:
        """Write an event with fields to the structured logger."""
        self._logger.log(level, event, **properties)


def check_supported_level(name: str, level: int) -> None:
    """Check whether structlog supports writing at this level.

    Validate when building the client rather than on the first request: otherwise a logging
    level typo becomes a `KeyError` inside structlog before the request is even sent;
    its record is built before the call.

    :param name: name of the parameter that supplied the level
    :param level: level to check
    :raises ValueError: if the level is not in `SUPPORTED_LOG_LEVELS`
    """
    if level in SUPPORTED_LOG_LEVELS:
        return

    supported = ", ".join(f"{logging.getLevelName(value)} ({value})" for value in SUPPORTED_LOG_LEVELS)
    message = f"structlog не умеет писать уровнем {level}: {name} принимает только {supported}"
    raise ValueError(message)
