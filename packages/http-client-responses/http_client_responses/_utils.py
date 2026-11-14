from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import ResponseNotRead

if TYPE_CHECKING:
    from httpx import Response

UNKNOWN = "?"
STREAMED_BODY = "<streamed content>"
DEFAULT_ENCODING = "utf-8"


def request_method(response: Response) -> str:
    """Return the HTTP method of the request that produced the response.

    :param response: Response to the request
    :returns: Request method, or `?` for a manually created response without a request
    """
    try:
        return response.request.method
    except RuntimeError:
        return UNKNOWN


def request_url(response: Response) -> str:
    """Return the URL of the request that produced the response.

    :param response: Response to the request
    :returns: Request URL, or `?` for a manually created response without a request
    """
    try:
        return str(response.url)
    except RuntimeError:
        return UNKNOWN


def body_preview(response: Response, limit: int) -> str:
    """Return a response body preview for an error message.

    :param response: Response to the request
    :param limit: Maximum body size in the result, in bytes
    :returns: Body truncated to `limit` bytes, or a placeholder for an unread stream
    """
    try:
        content = response.content
    except ResponseNotRead:
        return STREAMED_BODY

    encoding = response.encoding or DEFAULT_ENCODING
    if len(content) <= limit:
        return content.decode(encoding, errors="replace")

    # Truncate bytes before decoding: `response.text` would load the entire body into memory
    # for a few hundred characters. errors="replace" handles characters split at the boundary.
    head = content[:limit].decode(encoding, errors="replace")
    return f"{head}... (обрезано, всего {len(content)} байт)"
