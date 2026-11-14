from __future__ import annotations

from typing import TYPE_CHECKING, Self, TypeVar, cast

from pydantic import BaseModel

from ._utils import request_method, request_url
from .exceptions import ResponseParseError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta

    from httpx import Cookies, Headers, Request, Response

RT = TypeVar("RT")  # Response Type
RS = TypeVar("RS", bound=BaseModel)  # Response Schema


class _Unset:
    """Mark values not yet computed: None is a valid parsing result and needs a separate sentinel."""


_UNSET = _Unset()


class ResponseWrapper:
    """Base wrapper class for a request response."""

    def __init__(self, response: Response) -> None:
        """Initialize the object.

        :param response: Value of ``response``.
        """
        self.response = response

    def __repr__(self) -> str:
        """Get the response HTTP context for diagnostics."""
        method = request_method(self.response)
        return f"<{type(self).__name__} {method} {request_url(self.response)} -> {self.status_code}>"

    @property
    def status_code(self) -> int:
        """HTTP response status code."""
        return self.response.status_code

    @property
    def reason_phrase(self) -> str:
        """HTTP response reason phrase."""
        return self.response.reason_phrase

    @property
    def headers(self) -> Headers:
        """Response headers.

        Use `httpx.Headers`, rather than `dict`: key lookup is case-insensitive and `get_list()` returns
        all values of a header sent more than once by the server (such as `Set-Cookie`).
        """
        return self.response.headers

    @property
    def raw_headers(self) -> dict[str, str]:
        """Response headers as a plain dictionary.

        Repeated headers are joined into one comma-separated string; if this matters,
        use `headers`.
        """
        return dict(self.response.headers)

    @property
    def cookies(self) -> Cookies:
        """Response cookies."""
        return self.response.cookies

    @property
    def content(self) -> bytes:
        """Response body as bytes.

        :raises httpx.ResponseNotRead: If the response is streaming and its body has not been read
        """
        return self.response.content

    @property
    def text(self) -> str:
        """Response body as a string.

        :raises httpx.ResponseNotRead: If the response is streaming and its body has not been read
        """
        return self.response.text

    @property
    def url(self) -> str:
        """URL of the request that produced the response.

        :raises RuntimeError: If the response was created manually without a request
        """
        return str(self.response.url)

    @property
    def request(self) -> Request:
        """Request that produced the response.

        :raises RuntimeError: If the response was created manually without a request
        """
        return self.response.request

    @property
    def elapsed(self) -> timedelta:
        """Time between sending the request and receiving the response.

        :raises RuntimeError: If the response body has not been fully read
        """
        return self.response.elapsed

    @property
    def is_success(self) -> bool:
        """Check whether the status is in the 2xx range."""
        return self.response.is_success

    @property
    def is_error(self) -> bool:
        """Check whether the status is in the 4xx or 5xx range."""
        return self.response.is_error

    @property
    def is_client_error(self) -> bool:
        """Check whether the status is in the 4xx range."""
        return self.response.is_client_error

    @property
    def is_server_error(self) -> bool:
        """Check whether the status is in the 5xx range."""
        return self.response.is_server_error

    def raise_for_status(self) -> Self:
        """Check the response status.

        Return the wrapper itself to allow chained calls:
        `response.raise_for_status().model()`.

        :raises httpx.HTTPStatusError: If the response status is not 2xx, including 1xx and redirects
        :raises RuntimeError: If the response was created manually without a request
        :returns: The same object
        """
        self.response.raise_for_status()
        return self

    def json(self) -> object:
        """Parse the response body as JSON without schema validation.

        :raises ResponseParseError: If the body is not valid JSON
        :returns: Parsed response body
        """
        try:
            return cast("object", self.response.json())
        except Exception as exc:
            raise ResponseParseError(self.response, exc) from exc


class GenericResponse[RT](ResponseWrapper):
    """Response with a method for parsing body data."""

    def __init__(self, response: Response, parser: Callable[[Response], RT]) -> None:
        """Initialize the object.

        :param response: Value of ``response``.
        :param parser: Value of ``parser``.
        """
        super().__init__(response)
        self.parser = parser
        self._parsed: RT | _Unset = _UNSET

    def parse(self) -> RT:
        """Parse the response body.

        Compute the result once and reuse it for subsequent calls.

        :raises ResponseParseError: If the parser cannot parse the body
        :returns: Parser result
        """
        if self._parsed is _UNSET:
            try:
                self._parsed = self.parser(self.response)
            except Exception as exc:
                raise ResponseParseError(self.response, exc) from exc
        return cast("RT", self._parsed)


class JsonResponse[RS: BaseModel](GenericResponse[RS]):
    """Response with a JSON body schema represented by a pydantic model."""

    def __init__(self, response: Response, schema: type[RS]) -> None:
        """Initialize the object.

        :param response: Value of ``response``.
        :param schema: Value of ``schema``.
        """
        super().__init__(response, lambda r: schema.model_validate_json(r.content))
        self.schema = schema

    def model(self) -> RS:
        """Parse the response body into a pydantic model.

        :raises ResponseParseError: If the body does not match the schema
        :returns: Populated response schema model
        """
        return self.parse()
