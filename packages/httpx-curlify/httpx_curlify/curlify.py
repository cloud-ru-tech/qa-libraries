import json
from collections.abc import Callable, Sequence
from shlex import quote
from typing import TypedDict, Unpack, cast

import httpx2

from .sanitaizer import sanitize

_CREDENTIAL_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "api_key",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "password",
        "secret",
        "token",
    }
)


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
    request: httpx2.Request,
    sanitize_keys: Sequence[str] | None = None,
    json_dumps_kwargs: JsonDumpsOptions | None = None,
) -> str:
    """Serialize an HTTP request to a curl command string.

    :param request: HTTP request
    :param sanitize_keys: Custom glom paths replacing the default credential names.
        Pass an empty sequence to include the original values.
    :param json_dumps_kwargs: Formatting options for JSON bodies.
    :return: Curl command string
    """
    command = ["-X " + quote(request.method)]

    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    raw_headers = dict(request.headers)
    headers = _mask_credentials(raw_headers) if sanitize_keys is None else sanitize(raw_headers, sanitize_keys)
    for key, value in headers.items():
        if value:
            command.append("-H " + quote(f"{key}: {value}"))
        else:
            command.append("-H " + quote(f"{key};"))

    if content_type:
        request_body = request.read()
        try:
            payload = request_body.decode("utf-8")
        except UnicodeDecodeError:
            payload = f"<binary data {len(request_body)} bytes>"

        if content_type == "application/json" or content_type.endswith("+json"):
            if json_dumps_kwargs is None:
                json_dumps_kwargs = {}

            command.append(f"--json {quote(_format_json(payload, sanitize_keys, **json_dumps_kwargs))}")
        else:
            command.append(f"--data {quote(payload)}")

    command.append(quote(str(request.url)))

    return "curl " + " \\\n  ".join(command)


def _mask_credentials[T](fields: dict[str, T]) -> dict[str, T | str]:
    return {key: "****" if key.lower() in _CREDENTIAL_NAMES else value for key, value in fields.items()}


def _format_json(payload: str, sanitize_keys: Sequence[str] | None, **kwargs: Unpack[JsonDumpsOptions]) -> str:
    """Format a JSON string for readable output in a curl command.

    :param payload: JSON string
    :param sanitize_keys: Keys for masking secrets in JSON
    :param kwargs: Options for json.dumps
    :return: Formatted JSON string
    """
    if sanitize_keys is not None and not sanitize_keys and not kwargs:
        return payload
    if sanitize_keys is None:
        json_payload = cast("object", json.loads(payload, object_hook=_mask_credentials))
    else:
        json_payload = sanitize(cast("object", json.loads(payload)), sanitize_keys)

    formatted_payload = json.dumps(json_payload, **kwargs)

    lines = formatted_payload.split("\n")
    formatted_lines = lines[:1]

    for line in lines[1:]:
        formatted_lines.append(f"  {line}")

    return "\n".join(formatted_lines)
