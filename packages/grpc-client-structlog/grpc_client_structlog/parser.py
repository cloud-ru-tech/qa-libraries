import json
import logging
from typing import cast

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from grpc_client import RequestRecord, ResponseRecord
from grpc_client.types import MetadataType
from grpc_client.utils.logutils import PAYLOAD_UNAVAILABLE, TRUNCATION_SUFFIX, BytesEncoder, LogFormat
from grpc_client.utils.sanitizer import sanitize, sanitize_metadata

_logger = logging.getLogger(__name__)

# `body` field value when the request body is a message stream.
STREAMED_CONTENT = "<streamed content>"

# `status_code` contains the code name rather than its number: names need no reference lookup,
# and make filtering convenient. A number would add a second value to the field,
# whereas searching for `2 (UNKNOWN)` would require substring matching.

# `trace_id` is appended last to every record rather than set with the other fields:
# renderers that preserve insertion order (such as `structlog.processors.JSONRenderer`)
# output fields in this order, and the internal identifier must not split the call data.


def parse_request(record: RequestRecord, log_format: LogFormat) -> dict[str, object]:
    """Build structured log fields for a sent gRPC request.

    :param record: request data
    :param log_format: log formatting rules
    :returns: structured request log fields
    """
    properties: dict[str, object] = {
        "method": record.method,
        "body": _parse_body(record.message, log_format) if record.message is not None else STREAMED_CONTENT,
    }
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def parse_response(record: ResponseRecord, log_format: LogFormat) -> dict[str, object]:
    """Build structured log fields for a received gRPC response.

    :param record: completed call data
    :param log_format: log formatting rules
    :returns: structured response log fields
    """
    properties: dict[str, object] = {"method": record.method, "status_code": record.status_code.name}
    if record.message is not None:
        properties["body"] = _parse_body(record.message, log_format)
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def parse_stream_response(record: ResponseRecord, log_format: LogFormat) -> dict[str, object]:
    """Build structured log fields for a completed response message stream.

    Messages themselves are not logged: a stream may be arbitrarily long, and reading it
    for logging would change call behavior.

    :param record: completed stream data
    :param log_format: log formatting rules
    :returns: structured log fields for the completed stream
    """
    properties: dict[str, object] = {
        "method": record.method,
        "status_code": record.status_code.name,
        "messages_count": record.messages_count,
    }
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def parse_error(record: ResponseRecord, log_format: LogFormat) -> dict[str, object]:
    """Build structured log fields for a failed call.

    :param record: completed call data
    :param log_format: log formatting rules
    :returns: structured error log fields
    """
    properties: dict[str, object] = {
        "method": record.method,
        "status_code": record.status_code.name,
        "details": record.details,
    }
    if record.messages_count is not None:
        properties["messages_count"] = record.messages_count
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def _parse_metadata(metadata: MetadataType | None, log_format: LogFormat) -> str | None:
    """Build the metadata field value.

    Repeated key values are collected in a list: a regular dictionary would retain
    only the last value and make the log differ from the sent metadata.

    :param metadata: request or response metadata
    :param log_format: log formatting rules
    :returns: metadata as JSON, or None if absent
    """
    items = sanitize_metadata(metadata, log_format.sanitize_keys)
    if not items:
        return None

    grouped: dict[str, object] = {}
    for name, value in items:
        if name not in grouped:
            grouped[name] = value
        elif isinstance(previous := grouped[name], list):
            cast("list[object]", previous).append(value)
        else:
            grouped[name] = [grouped[name], value]

    return _to_json(grouped, log_format.json_indent)


def _parse_body(message: Message, log_format: LogFormat) -> str:
    """Build the message body field value.

    A log preparation error must not block requests: logs are built before sending, and a failure
    here, for example on a deeply nested message, would break the call itself.

    :param message: request or response message
    :param log_format: log formatting rules
    :returns: message body as JSON or a marker for an unavailable body
    """
    try:
        payload = cast("dict[str, object]", MessageToDict(message, always_print_fields_with_no_presence=True))
        masked = sanitize(payload, log_format.sanitize_keys)
        return _truncate(_to_json(masked, log_format.json_indent), log_format.payload_maxlength)
    except Exception:
        _logger.warning("Не удалось подготовить тело сообщения gRPC", exc_info=True)
        return PAYLOAD_UNAVAILABLE


def _to_json(value: dict[str, object], indent: int | None) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=False, cls=cast("type[json.JSONEncoder]", BytesEncoder))


def _truncate(value: str, maxlength: int | None) -> str:
    if maxlength is None or len(value) <= maxlength:
        return value
    return value[:maxlength] + TRUNCATION_SUFFIX
