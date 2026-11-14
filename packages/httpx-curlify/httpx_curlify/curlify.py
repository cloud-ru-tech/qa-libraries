import json
from collections.abc import Callable, Sequence
from shlex import quote
from typing import TypedDict, Unpack, cast

import httpx

from .sanitaizer import sanitize


class JsonDumpsOptions(TypedDict, total=False):
    """JSON serialization options passed to ``json.dumps``."""

    skipkeys: bool
    ensure_ascii: bool
    check_circular: bool
    allow_nan: bool
    indent: int | str | None
    separators: tuple[str, str] | None
    default: Callable[[object], object] | None
    cls: type[json.JSONEncoder] | None
    sort_keys: bool


def to_curl(
    request: httpx.Request,
    sanitize_keys: Sequence[str] = (),
    json_dumps_kwargs: JsonDumpsOptions | None = None,
) -> str:
    """Serialize an HTTP request to a curl command string.

    :param request: HTTP request
    :param sanitize_keys: Keys for masking secrets in the request
    :param json_dumps_kwargs: Options for json.dumps when the request has content-type = application/json
    :return: Curl command string
    """
    command = ["-X " + quote(request.method)]

    content_type: str | None = None

    headers = sanitize(dict(request.headers), sanitize_keys)
    for key, value in headers.items():
        if value:
            command.append("-H " + quote(f"{key}: {value}"))
        else:
            command.append("-H " + quote(f"{key};"))

        if key.lower() == "content-type":
            content_type = value.lower()

    if content_type:
        request_body = request.read()
        try:
            payload = request_body.decode("utf-8")
        except UnicodeDecodeError:
            payload = f"<binary data {len(request_body)} bytes>"

        if content_type.startswith("application/json"):
            if json_dumps_kwargs is None:
                json_dumps_kwargs = {}

            command.append(f"--json {quote(_format_json(payload, sanitize_keys, **json_dumps_kwargs))}")
        else:
            command.append(f"--data {quote(payload)}")

    command.append(quote(str(request.url)))

    return "curl " + " \\\n  ".join(command)


def _format_json(payload: str, sanitize_keys: Sequence[str], **kwargs: Unpack[JsonDumpsOptions]) -> str:
    """Format a JSON string for readable output in a curl command.

    :param payload: JSON string
    :param sanitize_keys: Keys for masking secrets in JSON
    :param kwargs: Options for json.dumps
    :return: Formatted JSON string
    """
    json_payload = sanitize(cast("object", json.loads(payload)), sanitize_keys)

    formatted_payload = json.dumps(json_payload, **kwargs)

    lines = formatted_payload.split("\n")
    formatted_lines = lines[:1]

    for line in lines[1:]:
        formatted_lines.append(f"  {line}")

    return "\n".join(formatted_lines)
