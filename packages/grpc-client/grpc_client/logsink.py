import logging
from dataclasses import dataclass
from typing import Protocol

import grpc
from google.protobuf.message import Message

from .config import LOGGING_CONFIG
from .types import MetadataType
from .utils import logutils
from .utils.logutils import LogFormat


def resolve_log_levels(log_level: int | None = None, err_log_level: int | None = None) -> tuple[int, int]:
    """Replace `None` levels with values from the shared configuration.

    Useful when effective levels are needed before building a client, for example to
    reject an output level unsupported by the sink in advance.

    :param log_level: successful request logging level
    :param err_log_level: failed request logging level
    :return: pair of success and error levels
    """
    return (
        log_level if log_level is not None else LOGGING_CONFIG.log_level,
        err_log_level if err_log_level is not None else LOGGING_CONFIG.err_log_level,
    )


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Sent gRPC request."""

    # Identifier linking a request to its response.
    trace_id: str

    # Full name of the method to call as /package.Service/Method.
    method: str

    # Sent message. `None` when the request body is a message stream.
    message: Message | None

    # Request metadata.
    metadata: MetadataType | None


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    """Completed gRPC call: successful, failed, or a completed stream."""

    # Identifier linking a request to its response.
    trace_id: str

    # Full name of the called method as /package.Service/Method.
    method: str

    # Final call status code.
    status_code: grpc.StatusCode

    # Response message. `None` for streaming responses and failed calls.
    message: Message | None

    # Service error text. Empty for successful calls.
    details: str

    # Response metadata.
    metadata: MetadataType | None

    # Number of received messages. `None` for unary responses.
    messages_count: int | None

    @property
    def succeeded(self) -> bool:
        """Whether the call completed successfully."""
        return self.status_code is grpc.StatusCode.OK

    @property
    def is_stream(self) -> bool:
        """Whether the record describes a completed response stream."""
        return self.messages_count is not None


class LogSink(Protocol):
    """Sink for gRPC call records.

    The interceptor builds records and selects levels; the sink decides where and how
    records are written. Connect an implementation using `options.with_log_sink`.

    Implementation requirements:

    - methods run in different threads; the final response stream log is written from the internal
      grpcio channel thread, while asynchronous logs run in an event loop task;
    - slow methods delay the call itself: requests are logged before sending;
    - interceptor suppresses sink exceptions without breaking the call, but the record is lost.
    """

    def is_enabled_for(self, level: int) -> bool:
        """Check whether records at the specified level reach the output.

        The interceptor asks before building a record: preparing a message body costs
        more than the query itself. When both levels are disabled, the interceptor does
        nothing: it neither generates an identifier nor wraps the stream to count messages.

        :param level: record level
        :return: True if a record at this level reaches output
        """
        ...

    def write_request(self, level: int, record: RequestRecord) -> None:
        """Log a sent request.

        :param level: record level
        :param record: request data
        """
        ...

    def write_response(self, level: int, record: ResponseRecord) -> None:
        """Log a completed call.

        :param level: record level
        :param record: completed call data
        """
        ...


class TextLogSink:
    """Sink that writes records as one line to a stdlib logger."""

    def __init__(self, logger: logging.Logger, log_format: LogFormat | None = None) -> None:
        """Initialize the object.

        :param logger: logger used for requests and responses
        :param log_format: log formatting rules, defaults to shared configuration
        """
        self._logger = logger
        self._format = log_format if log_format is not None else LogFormat.from_config()

    def is_enabled_for(self, level: int) -> bool:
        """Check whether the logger writes records at the specified level."""
        return self._logger.isEnabledFor(level)

    def write_request(self, level: int, record: RequestRecord) -> None:
        """Log a sent request."""
        self._logger.log(
            level,
            logutils.request_log(
                trace_id=record.trace_id,
                method=record.method,
                message=record.message,
                metadata=record.metadata,
                log_format=self._format,
            ),
        )

    def write_response(self, level: int, record: ResponseRecord) -> None:
        """Log a completed call."""
        self._logger.log(level, self._response_text(record))

    def _response_text(self, record: ResponseRecord) -> str:
        """Build a log line suitable for the call outcome."""
        if not record.succeeded:
            return logutils.error_log(
                trace_id=record.trace_id,
                method=record.method,
                status_code=record.status_code,
                details=record.details,
                metadata=record.metadata,
                log_format=self._format,
            )

        if record.messages_count is not None:
            return logutils.stream_response_log(
                trace_id=record.trace_id,
                method=record.method,
                status_code=record.status_code,
                messages_count=record.messages_count,
                metadata=record.metadata,
                log_format=self._format,
            )

        return logutils.response_log(
            trace_id=record.trace_id,
            method=record.method,
            status_code=record.status_code,
            message=record.message,
            metadata=record.metadata,
            log_format=self._format,
        )
