import json
from collections.abc import Sequence
from typing import cast
from urllib.parse import urlencode

import httpx
from http_client.utils import sanitizer

STREAMED_CONTENT = "<streamed content>"

JSON_CONTENT_TYPE = "application/json"


def decode(body: bytes) -> str:
    """Decode a request or response body without failing on binary data."""
    try:
        return body.decode()
    except UnicodeDecodeError:
        return f"<binary data {len(body)} bytes>"


class Unparsed:
    """Marker for a body that could not be parsed as JSON.

    Use a separate type because both None and str can be valid parsed values.
    """


UNPARSED = Unparsed()


def parse_json_body(text: str, sanitize_keys: Sequence[str]) -> object:
    """Parse a JSON body and mask its secrets.

    :param text: Text representation of the body
    :param sanitize_keys: Keys in glom format for masking secrets
    :return: Parsed value, or UNPARSED if the body is not JSON
    """
    try:
        parsed = cast("object", json.loads(text))
    except json.JSONDecodeError:
        return UNPARSED

    # Keep branches separate: the sanitize TypeVar is constrained to dict and list and cannot accept a union.
    if isinstance(parsed, dict):
        return sanitizer.sanitize(cast("dict[str, object]", parsed), sanitize_keys)

    if isinstance(parsed, list):
        return sanitizer.sanitize(cast("list[object]", parsed), sanitize_keys)

    return parsed


def render_body(
    body: bytes | None,
    content_type: str,
    sanitize_keys: Sequence[str],
) -> object:
    """Prepare a body for serialization as an attachment.

    :param body: Request or response body; None indicates an unread stream
    :param content_type: Content-Type header value
    :param sanitize_keys: Keys in glom format for masking secrets
    :return: Parsed and masked JSON, or a text representation of the body
    """
    if body is None:
        return STREAMED_CONTENT

    text = decode(body)
    if not content_type.startswith(JSON_CONTENT_TYPE):
        return text

    parsed = parse_json_body(text, sanitize_keys)

    # The header declared JSON but the body is not JSON; display it unchanged because
    # report formatting must not break the request.
    return text if parsed is UNPARSED else parsed


QueryParams = dict[str, str | list[str]]


def sanitize_query_params(request: httpx.Request, sanitize_keys: Sequence[str]) -> QueryParams:
    """Return request query parameters with secrets masked.

    Collect repeated keys into a list to keep the report consistent with
    what was sent to the server: otherwise `tag=a&tag=b` would become only `tag=a`.
    """
    params: QueryParams = {}

    for key, value in request.url.params.multi_items():
        existing = params.get(key)
        if existing is None:
            params[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            params[key] = [existing, value]

    return sanitizer.sanitize(params, sanitize_keys)


def encode_query_params(params: QueryParams) -> str:
    """Build a query string while preserving repeated keys."""
    pairs: list[tuple[str, str]] = []

    for key, value in params.items():
        if isinstance(value, list):
            pairs.extend((key, item) for item in value)
        else:
            pairs.append((key, value))

    # safe="*" prevents the **** mask from becoming %2A%2A%2A%2A
    return urlencode(pairs, safe="*")
