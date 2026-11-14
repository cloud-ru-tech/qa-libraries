import codecs
import json
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import cast
from uuid import uuid4

from glom import GlomError
from httpx import Request, Response

from http_client.config import LOGGING_CONFIG as CFG

from .sanitizer import sanitize

ELLIPSIS = "..."
DEFAULT_ENCODING = "utf-8"

__all__ = [
    "create_request_log",
    "create_response_log",
    "create_response_log_async",
    "decode",
    "is_buffered",
    "is_streamed",
    "parse_error",
    "to_json",
    "trim",
]


def create_request_log(
    r: Request,
    sanitize_keys: Sequence[str],
    json_indent: int | None = None,
    *,
    use_line_breaks: bool = True,
) -> str:
    """Build an HTTP request log.

    :param r: Request containing data to log
    :param sanitize_keys: Keys in [glom](https://glom.readthedocs.io/en/latest/) format,
                          to mask in request data
    :param json_indent: JSON indentation width (no indentation by default)
    :param use_line_breaks: Whether to add line breaks between request properties
    :returns: Request log
    """
    # NOTE: trace_id here only correlates the request and response.
    # It is unrelated to the trace_id of a server with telemetry enabled.
    trace_id = str(uuid4())
    extensions = cast("dict[str, object]", r.extensions)
    extensions["trace_id"] = trace_id

    log_parts = [
        f"Request: id={trace_id}",
        f"Method: [{r.method.upper()}] {r.url.scheme}://{r.url.host}{r.url.path}",
    ]

    _add_query_params(r, log_parts, sanitize_keys, json_indent)
    _add_headers(r, log_parts, sanitize_keys, json_indent)
    _add_body(r, log_parts, sanitize_keys, json_indent, streamed=not is_buffered(r))

    sep = _sep(use_line_breaks=use_line_breaks)
    return sep.join(log_parts)


def create_response_log(
    r: Response,
    sanitize_keys: Sequence[str],
    json_indent: int | None = None,
    *,
    use_line_breaks: bool = True,
) -> str:
    """Build an HTTP response log.

    :param r: Response containing data to log
    :param sanitize_keys: Keys in [glom](https://glom.readthedocs.io/en/latest/) format,
                          to mask in response data
    :param json_indent: JSON indentation width (no indentation by default)
    :param use_line_breaks: Whether to add line breaks between request properties
    :returns: Response log
    """
    extensions = cast("dict[str, object]", r.request.extensions)
    trace_id = extensions.get("trace_id", "<none>")

    log_parts = [f"Response: id={trace_id}", f"Status: {r.status_code} [{r.reason_phrase}]"]

    _add_headers(r, log_parts, sanitize_keys, json_indent)
    _add_body(r, log_parts, sanitize_keys, json_indent, streamed=is_streamed(r))

    sep = _sep(use_line_breaks=use_line_breaks)
    return sep.join(log_parts)


async def create_response_log_async(
    r: Response,
    sanitize_keys: Sequence[str],
    json_indent: int | None = None,
    *,
    use_line_breaks: bool = True,
) -> str:
    """Build an asynchronous client response log.

    The httpx response hook runs before the client finishes reading the body, so
    an asynchronous response still has an asynchronous stream that cannot use synchronous read().

    :returns: Response log
    """
    await _aread_buffered(r)
    return create_response_log(r, sanitize_keys, json_indent, use_line_breaks=use_line_breaks)


async def _aread_buffered(r: Response) -> None:
    """Finish reading a non-streaming response body."""
    if is_streamed(r):
        return

    # Logging must not fail the request: _add_body handles unreadable bodies.
    with suppress(Exception):
        await r.aread()


def _add_query_params(
    r: Request,
    log_parts: list[str],
    sanitize_keys: Sequence[str],
    json_indent: int | None,
) -> None:
    """Add query parameters to the log."""
    if not r.url.query:
        return

    try:
        sanitized_params = sanitize(dict(r.url.params.items()), sanitize_keys)
        log_parts.append(f"QueryParams: {to_json(sanitized_params, json_indent)}")
    except (TypeError, ValueError, GlomError) as e:
        log_parts.append(f"QueryParams: {parse_error(e)}")


def _add_headers(
    r: Request | Response,
    log_parts: list[str],
    sanitize_keys: Sequence[str],
    json_indent: int | None,
) -> None:
    """Add HTTP headers to the log."""
    try:
        sanitized_headers = sanitize(dict(r.headers.items()), sanitize_keys)
        log_parts.append(f"Headers: {to_json(sanitized_headers, json_indent)}")
    except (TypeError, ValueError, GlomError) as e:
        log_parts.append(f"Headers: {parse_error(e)}")


def _add_body(
    r: Request | Response,
    log_parts: list[str],
    sanitize_keys: Sequence[str],
    json_indent: int | None,
    *,
    streamed: bool,
) -> None:
    """Add the request or response body to the log."""
    if streamed:
        log_parts.append("Body: <streamed content>")
        return

    headers: Mapping[str, str] = r.headers
    content_type = headers.get("Content-Type", "").lower()
    try:
        if content_type.startswith("application/json"):
            decoded_body = cast("object", json.loads(r.read()))
            sanitized_body = sanitize(decoded_body, sanitize_keys)
            log_parts.append(f"Body: {trim(to_json(sanitized_body, json_indent), CFG.json_log_maxlength)}")
        elif content_type.startswith("text/plain"):
            log_parts.append(f"Body: {trim(decode(r), CFG.plain_text_log_maxlength)}")
        elif content_type.startswith("application/octet-stream"):
            log_parts.append(f"Body: {_octet_stream(r.read())}")
        elif content_type:
            log_parts.append(f"Body: <not logged, content-type: {content_type}>")
    except (TypeError, ValueError, GlomError, RuntimeError, OSError) as e:
        log_parts.append(f"Body: {parse_error(e)}")


def _octet_stream(content: bytes) -> str:
    try:
        return trim(content.decode(), CFG.octet_stream_log_maxlength)
    except UnicodeDecodeError:
        return f"<binary content ({len(content)} bytes)>"


def is_streamed(r: Response) -> bool:
    """Check whether a response is streaming and unread."""
    extensions = cast("dict[str, object]", r.request.extensions)
    return bool(extensions.get("is_streaming", False)) and not r.is_stream_consumed


def is_buffered(r: Request) -> bool:
    """Check whether the request body is in memory.

    Reading a streaming request body would consume the stream before sending it.
    """
    return hasattr(r, "_content")


def decode(r: Request | Response) -> str:
    """Decode the body using the charset from Content-Type."""
    content = r.read()
    headers: Mapping[str, str] = r.headers
    return content.decode(_charset(headers.get("Content-Type", "")), errors="replace")


def _charset(content_type: str) -> str:
    """Extract the encoding from Content-Type.

    A header may have multiple parameters (`text/plain; charset=utf-8; format=flowed`),
    so select charset by its parameter name rather than taking everything after `charset=`.
    Replace unknown encodings with utf-8 to avoid hiding the body.
    """
    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() != "charset":
            continue

        charset = value.strip().strip("\"'")
        if not charset:
            break

        try:
            codecs.lookup(charset)
        except LookupError:
            break

        return charset

    return DEFAULT_ENCODING


def parse_error(e: Exception) -> str:
    """Build a safe description of a parsing error.

    Do not include exception text: it may contain body fragments or URLs with secrets.
    """
    return f"<Error parse: {type(e).__name__}>"


def to_json(value: object, indent: int | None) -> str:
    """Serialize a value to JSON while preserving Unicode.

    :param value: Value to serialize
    :param indent: Indentation width
    :returns: JSON representation
    """
    return json.dumps(value, indent=indent, ensure_ascii=False)


def trim(text: str, length: int | None) -> str:
    """Truncate a string while preserving its beginning and end.

    :param text: Original string
    :param length: Length limit; None and nonpositive numbers disable it
    :returns: Original or truncated string
    """
    if not length or length < 0 or len(text) <= length:
        return text

    if length <= len(ELLIPSIS):
        return ELLIPSIS[:length]

    payload = length - len(ELLIPSIS)
    tail = payload // 2
    head = payload - tail
    return text[:head] + ELLIPSIS + (text[-tail:] if tail else "")


def _sep(*, use_line_breaks: bool) -> str:
    return "\n" if use_line_breaks else " "
