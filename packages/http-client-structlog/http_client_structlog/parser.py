import json
import logging
from contextlib import suppress
from typing import cast
from uuid import uuid4

import httpx
from http_client.config import LOGGING_CONFIG as CFG
from http_client.utils.logutils import decode, is_buffered, is_streamed, parse_error, to_json, trim

from .sanitizer import Sanitizer

STREAMED_CONTENT = "<streamed content>"
UNKNOWN_TRACE_ID = "<without trace_id>"
_logger = logging.getLogger(__name__)


def parse_request(
    request: httpx.Request,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
) -> dict[str, object]:
    """Parse fields for a structured HTTP request log.

    :param request: Request containing data to log
    :param sanitizer: Sensitive data masking rules
    :param json_indent: JSON log indentation width
    :return: Structured request log fields
    """
    # NOTE: trace_id here only correlates the request and response.
    # It is unrelated to the trace_id of a server with telemetry enabled.
    trace_id = str(uuid4())
    extensions = cast("dict[str, object]", request.extensions)
    extensions["trace_id"] = trace_id

    properties: dict[str, object] = {
        "method": request.method.upper(),
        "url": f"{request.url.scheme}://{request.url.host}{request.url.path}",
        "headers": _parse_headers(request, sanitizer, json_indent),
        "trace_id": trace_id,
    }

    if request.url.params:
        properties["query_params"] = _parse_query_params(request, sanitizer, json_indent)

    if (body := _parse_body(request, sanitizer, json_indent)) is not None:
        properties["body"] = body

    return properties


def parse_response(
    response: httpx.Response,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
) -> dict[str, object]:
    """Parse fields for a structured HTTP response log.

    :param response: Response containing data to log
    :param sanitizer: Sensitive data masking rules
    :param json_indent: JSON log indentation width
    :return: Structured response log fields
    """
    properties: dict[str, object] = {
        "status_code": response.status_code,
        "headers": _parse_headers(response, sanitizer, json_indent),
        "trace_id": cast("dict[str, object]", response.request.extensions).get("trace_id", UNKNOWN_TRACE_ID),
    }

    if (body := _parse_body(response, sanitizer, json_indent)) is not None:
        properties["body"] = body

    return properties


async def parse_response_async(
    response: httpx.Response,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
) -> dict[str, object]:
    """Parse fields for a structured asynchronous client response log.

    The httpx response hook runs before the client finishes reading the body, so
    an asynchronous response still has an asynchronous stream that cannot use synchronous read().

    :return: Structured response log fields
    """
    await _aread_buffered(response)
    return parse_response(response, sanitizer, json_indent)


async def _aread_buffered(response: httpx.Response) -> None:
    """Finish reading a non-streaming response body."""
    if is_streamed(response):
        return

    # Logging must not fail the request: _parse_body handles unreadable bodies.
    with suppress(Exception):
        await response.aread()


def _parse_headers(
    r: httpx.Request | httpx.Response,
    sanitizer: Sanitizer,
    json_indent: int | None,
) -> str:
    try:
        return to_json(sanitizer.apply(dict[str, str](r.headers)), json_indent)
    except Exception as error:
        _logger.exception(  # noqa: LOG007 — A traceback may expose request contents
            "Не удалось подготовить поле HTTP лога: %s",
            type(error).__name__,
            exc_info=False,
        )
        return parse_error(error)


def _parse_query_params(
    request: httpx.Request,
    sanitizer: Sanitizer,
    json_indent: int | None,
) -> str:
    try:
        return to_json(sanitizer.apply(dict[str, str](request.url.params)), json_indent)
    except Exception as error:
        _logger.exception(  # noqa: LOG007 — A traceback may expose request contents
            "Не удалось подготовить поле HTTP лога: %s",
            type(error).__name__,
            exc_info=False,
        )
        return parse_error(error)


def _parse_body(
    value: httpx.Request | httpx.Response,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
) -> str | None:
    if isinstance(value, cast("type[object]", httpx.Response)):
        streamed = is_streamed(cast("httpx.Response", value))
    else:
        streamed = not is_buffered(cast("httpx.Request", value))
    if streamed:
        return STREAMED_CONTENT

    try:
        content = value.read()
        content_type = cast("str", value.headers.get("Content-Type", "")).lower()
        return _render_content(content, content_type, value, sanitizer, json_indent)
    except Exception as error:
        _logger.exception(  # noqa: LOG007 — A traceback may expose request contents
            "Не удалось подготовить тело HTTP лога: %s",
            type(error).__name__,
            exc_info=False,
        )
        return parse_error(error)


def _render_content(
    content: bytes,
    content_type: str,
    value: httpx.Request | httpx.Response,
    sanitizer: Sanitizer,
    json_indent: int | None,
) -> str | None:
    if not content:
        return None
    if content_type.startswith("application/json"):
        sanitized_body = sanitizer.apply(cast("object", json.loads(content)))
        return trim(to_json(sanitized_body, json_indent), CFG.json_log_maxlength)
    if content_type.startswith("text/plain"):
        return trim(decode(value), CFG.plain_text_log_maxlength)
    if content_type.startswith("application/octet-stream"):
        return _render_octet_stream(content)
    return f"<not logged, content-type: {content_type}>" if content_type else None


def _render_octet_stream(content: bytes) -> str:
    try:
        return trim(content.decode(), CFG.octet_stream_log_maxlength)
    except UnicodeDecodeError:
        return f"<binary content ({len(content)} bytes)>"
