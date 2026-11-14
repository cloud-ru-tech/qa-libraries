from __future__ import annotations

from typing import TYPE_CHECKING

from ._utils import body_preview, request_method, request_url

if TYPE_CHECKING:
    from httpx import Response


class ResponseParseError(Exception):
    """Failed to parse the response body.

    Wrap the original parsing error with HTTP context: method, URL,
    status and response body. The original exception is available through `cause` and `__cause__`.

    Truncate the body in the message to `BODY_PREVIEW_LIMIT` bytes. For a streaming
    response whose body has not been read, use `<streamed content>` instead.
    """

    BODY_PREVIEW_LIMIT = 512

    def __init__(self, response: Response, cause: Exception) -> None:
        """Initialize the object.

        :param response: Value of ``response``.
        :param cause: Value of ``cause``.
        """
        self.response = response
        self.cause = cause
        super().__init__(self._build_message(response, cause))

    @classmethod
    def _build_message(cls, response: Response, cause: Exception) -> str:
        return (
            "не удалось разобрать тело ответа\n"
            f"  {request_method(response)} {request_url(response)} -> {response.status_code}\n"
            f"  Body: {body_preview(response, cls.BODY_PREVIEW_LIMIT)}\n"
            f"  Причина: {cause}"
        )
