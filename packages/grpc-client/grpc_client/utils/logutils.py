import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypedDict, Unpack, cast, override

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from grpc_client.config import LOGGING_CONFIG
from grpc_client.types import MetadataType

from .sanitizer import DEFAULT_SANITIZE_KEYS, sanitize, sanitize_metadata

TRUNCATION_SUFFIX = "... <обрезано>"


class FormatOptions(TypedDict, total=False):
    """Log record formatting options."""

    sanitize_keys: Sequence[str] | None
    json_indent: int | None
    use_line_breaks: bool | None
    payload_maxlength: int | None
    use_default_sanitize_keys: bool


class LoggerOptions(FormatOptions, total=False):
    """Log record formatting and levels."""

    log_level: int | None
    err_log_level: int | None


class BytesEncoder(json.JSONEncoder):
    """Encoder that converts bytes to strings."""

    @override
    def default(self, o: object) -> object:
        if isinstance(o, bytes):
            try:
                return o.decode("utf-8")
            except UnicodeDecodeError:
                return "<двоичные данные>"
        return cast("object", super().default(o))


@dataclass(frozen=True, slots=True, kw_only=True)
class LogFormat:
    """Formatting rules for gRPC request and response logs."""

    # Metadata keys and glom paths in the message body whose values are masked.
    sanitize_keys: Sequence[str] = field(default_factory=tuple)

    # Indentation width for formatting JSON.
    json_indent: int | None = None

    # Whether to put log properties on separate lines.
    use_line_breaks: bool = False

    # Maximum logged message body length.
    payload_maxlength: int | None = None

    @property
    def separator(self) -> str:
        """Log property separator."""
        return "\n" if self.use_line_breaks else " "

    @classmethod
    def from_config(
        cls,
        *,
        sanitize_keys: Sequence[str] | None = None,
        json_indent: int | None = None,
        use_line_breaks: bool | None = None,
        payload_maxlength: int | None = None,
        use_default_sanitize_keys: bool = True,
    ) -> "LogFormat":
        """Build formatting rules, replacing `None` with shared configuration values.

        Configuration is read when called, so `configure_logging` must run
        before building the client.

        :param sanitize_keys: metadata key names and message body glom paths whose values are masked
        :param json_indent: JSON indentation width, defaults to configuration
        :param use_line_breaks: whether to put log properties on separate lines, defaults to configuration
        :param payload_maxlength: maximum logged message body length, defaults to configuration
        :param use_default_sanitize_keys: whether to mask common secrets in addition to `sanitize_keys`
        :return: log formatting rules
        """
        keys = list(sanitize_keys or [])
        if use_default_sanitize_keys:
            keys.extend(key for key in DEFAULT_SANITIZE_KEYS if key not in keys)

        return cls(
            sanitize_keys=tuple(keys),
            json_indent=json_indent if json_indent is not None else LOGGING_CONFIG.json_indent,
            use_line_breaks=use_line_breaks if use_line_breaks is not None else LOGGING_CONFIG.use_line_breaks,
            payload_maxlength=(
                payload_maxlength if payload_maxlength is not None else LOGGING_CONFIG.payload_log_maxlength
            ),
        )


def request_log(
    trace_id: str,
    method: str,
    message: Message | None,
    metadata: MetadataType | None,
    log_format: LogFormat,
) -> str:
    """Build a log entry for a sent gRPC request.

    :param trace_id: identifier linking a request to its response
    :param method: full name of the method to call
    :param message: sent message, absent for client streams
    :param metadata: request metadata
    :param log_format: log formatting rules
    :return: log line
    """
    parts = [f"GRPC request sent: id={trace_id}", f"Method: {method}"]
    parts.append(f"Payload: {_payload(message, log_format)}" if message is not None else "Payload: <поток сообщений>")
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


class ResponseLogFields(TypedDict):
    """Log record data."""

    trace_id: str
    method: str
    status_code: grpc.StatusCode
    message: Message | None
    metadata: MetadataType | None
    log_format: LogFormat


def response_log(**fields: Unpack[ResponseLogFields]) -> str:
    """Build a log entry for a received gRPC response.

    :param trace_id: identifier linking a request to its response
    :param method: full name of the called method
    :param status_code: response status code
    :param message: response message, absent for server streams
    :param metadata: response metadata
    :param log_format: log formatting rules
    :return: log line
    """
    trace_id = fields["trace_id"]
    method = fields["method"]
    status_code = fields["status_code"]
    message = fields["message"]
    metadata = fields["metadata"]
    log_format = fields["log_format"]
    parts = [
        f"GRPC response received: id={trace_id}",
        f"Status: {_status(status_code)}",
        f"Method: {method}",
    ]
    if message is not None:
        parts.append(f"Payload: {_payload(message, log_format)}")
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


class StreamResponseLogFields(TypedDict):
    """Log record data."""

    trace_id: str
    method: str
    status_code: grpc.StatusCode
    messages_count: int
    metadata: MetadataType | None
    log_format: LogFormat


def stream_response_log(**fields: Unpack[StreamResponseLogFields]) -> str:
    """Build a log entry for a completed response message stream.

    Messages themselves are not logged: a stream may be arbitrarily long, and reading it
    for logging would change call behavior.

    :param trace_id: identifier linking a request to its response
    :param method: full name of the called method
    :param status_code: final stream status code
    :param messages_count: number of received messages
    :param metadata: response metadata
    :param log_format: log formatting rules
    :return: log line
    """
    trace_id = fields["trace_id"]
    method = fields["method"]
    status_code = fields["status_code"]
    messages_count = fields["messages_count"]
    metadata = fields["metadata"]
    log_format = fields["log_format"]
    parts = [
        f"GRPC stream finished: id={trace_id}",
        f"Status: {_status(status_code)}",
        f"Method: {method}",
        f"Messages: {messages_count}",
    ]
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


class ErrorLogFields(TypedDict):
    """Log record data."""

    trace_id: str
    method: str
    status_code: grpc.StatusCode
    details: str
    metadata: MetadataType | None
    log_format: LogFormat


def error_log(**fields: Unpack[ErrorLogFields]) -> str:
    """Build a log entry for a failed gRPC request.

    :param trace_id: identifier linking a request to its response
    :param method: full name of the called method
    :param status_code: response status code
    :param details: service error text
    :param metadata: response metadata
    :param log_format: log formatting rules
    :return: log line
    """
    trace_id = fields["trace_id"]
    method = fields["method"]
    status_code = fields["status_code"]
    details = fields["details"]
    metadata = fields["metadata"]
    log_format = fields["log_format"]
    parts = [
        f"GRPC error occurred: id={trace_id}",
        f"Status: {_status(status_code)}",
        f"Method: {method}",
        f"Error: {details}",
    ]
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


def _status(status_code: grpc.StatusCode) -> str:
    """Build a text representation of the status code."""
    code, _ = cast("tuple[int, str]", status_code.value)
    return f"{code} ({status_code.name})"


def _metadata_parts(metadata: MetadataType | None, log_format: LogFormat) -> list[str]:
    """Build the metadata portion of the log.

    Repeated key values are collected in a list: a regular dictionary would retain
    only the last value and make the log differ from the sent metadata.
    """
    items = sanitize_metadata(metadata, log_format.sanitize_keys)
    if not items:
        return []

    grouped: dict[str, object] = {}
    for name, value in items:
        if name not in grouped:
            grouped[name] = value
        elif isinstance(previous := grouped[name], list):
            cast("list[object]", previous).append(value)
        else:
            grouped[name] = [grouped[name], value]

    return [f"Metadata: {_to_json(grouped, log_format.json_indent)}"]


PAYLOAD_UNAVAILABLE = "<не удалось подготовить тело сообщения>"


def _payload(message: Message, log_format: LogFormat) -> str:
    """Build the message body portion of the log.

    A log preparation error must not block requests: logs are built before sending, and a failure
    here, for example on a deeply nested message, would break the call itself.
    """
    try:
        payload = cast("dict[str, object]", MessageToDict(message, always_print_fields_with_no_presence=True))
        masked = sanitize(payload, log_format.sanitize_keys)
        return _truncate(_to_json(masked, log_format.json_indent), log_format.payload_maxlength)
    except RecursionError:
        return PAYLOAD_UNAVAILABLE
    except Exception:  # noqa: BLE001 - both glom path errors and serialization failures reach here
        return PAYLOAD_UNAVAILABLE


def _to_json(value: dict[str, object], indent: int | None) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=False, cls=cast("type[json.JSONEncoder]", BytesEncoder))


def _truncate(value: str, maxlength: int | None) -> str:
    if maxlength is None or len(value) <= maxlength:
        return value
    return value[:maxlength] + TRUNCATION_SUFFIX
