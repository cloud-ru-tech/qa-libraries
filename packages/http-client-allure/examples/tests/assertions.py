from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

import httpx
from assertpy.assertpy import AssertionBuilder
from tenacity import RetryError

if TYPE_CHECKING:
    _Builder = AssertionBuilder[object]
else:
    _Builder = AssertionBuilder


class HttpbinAssertions(_Builder):
    """Assertions for httpbin responses.

    Hide httpbin echo parsing and RetryError unpacking so the test body
    describes only the expected behavior.
    """

    def has_status(self, expected: int) -> Self:
        """Check the response status code."""
        actual = cast("httpx.Response", self.val).status_code
        if actual != expected:
            self.error(f"Expected status <{expected}>, but was <{actual}>")

        return self

    def has_text(self, expected: str) -> Self:
        """Check the text response body."""
        actual = cast("httpx.Response", self.val).text
        if actual != expected:
            self.error(f"Expected body <{expected}>, but was <{actual}>")

        return self

    def has_empty_body(self) -> Self:
        """Check that the response body is empty."""
        actual = cast("httpx.Response", self.val).content
        if actual:
            self.error(f"Expected an empty body, but was <{actual!r}>")

        return self

    def has_response_header(self, name: str, expected: str) -> Self:
        """Check a header returned by the server."""
        actual = cast("str | None", cast("httpx.Response", self.val).headers.get(name))
        if actual != expected:
            self.error(f"Expected response header <{name}> to be <{expected}>, but was <{actual}>")

        return self

    def hits_path(self, expected: str) -> Self:
        """Check the final request path after redirects."""
        actual = cast("httpx.Response", self.val).url.path
        if actual != expected:
            self.error(f"Expected the request to land on <{expected}>, but landed on <{actual}>")

        return self

    def has_json_field(self, path: str, *, expected: object) -> Self:
        """Check a response body field using a dotted path."""
        actual = _read_field(self._body(), path)
        if actual != expected:
            self.error(f"Expected field <{path}> to be <{expected}>, but was <{actual}>")

        return self

    def have_distinct_json_field(self, path: str) -> Self:
        """Check that each response in the list has its own field value."""
        values = [
            _read_field(cast("object", response.json()), path) for response in cast("list[httpx.Response]", self.val)
        ]
        if len(set(values)) != len(values):
            self.error(f"Expected every response to carry its own <{path}>, but was <{values}>")

        return self

    def echoes_json(self, expected: object) -> Self:
        """Check the JSON request body echoed by httpbin."""
        actual = self._body()["json"]
        if actual != expected:
            self.error(f"Expected httpbin to echo <{expected}>, but echoed <{actual}>")

        return self

    def echoes_body(self, expected: str) -> Self:
        """Check the raw request body echoed by httpbin."""
        actual = self._body()["data"]
        if actual != expected:
            self.error(f"Expected httpbin to echo <{expected}>, but echoed <{actual}>")

        return self

    def echoes_query_param(self, name: str, expected: list[str]) -> Self:
        """Check a query parameter received by the server."""
        actual = cast("dict[str, list[str]]", self._body()["args"]).get(name)
        if actual != expected:
            self.error(f"Expected query parameter <{name}> to be <{expected}>, but was <{actual}>")

        return self

    def echoes_header(self, name: str, expected: list[str]) -> Self:
        """Check a header received by the server."""
        actual = self._headers().get(name.lower())
        if actual != expected:
            self.error(f"Expected header <{name}> to be <{expected}>, but was <{actual}>")

        return self

    def carries_header(self, name: str) -> Self:
        """Check that the header reached the server with a nonempty value."""
        actual = self._headers().get(name.lower())
        if not actual or not all(actual):
            self.error(f"Expected header <{name}> to carry a value, but was <{actual}>")

        return self

    def kept_response_with_status(self, expected: int) -> Self:
        """Check the last attempt response stored in RetryError."""
        error = self.val
        if not isinstance(error, RetryError):
            self.error(f"Expected <RetryError>, but was <{type(error).__name__}>")

        response = cast("object", cast("RetryError", error).last_attempt.result())
        if not isinstance(response, cast("type[object]", httpx.Response)):
            self.error(f"Expected RetryError to keep an <httpx.Response>, but kept <{type(response).__name__}>")

        status = cast("httpx.Response", response).status_code
        if status != expected:
            self.error(f"Expected the last attempt to answer <{expected}>, but answered <{status}>")

        return self

    def _body(self) -> dict[str, object]:
        return cast("dict[str, object]", cast("httpx.Response", self.val).json())

    def _headers(self) -> dict[str, list[str]]:
        return {name.lower(): values for name, values in cast("dict[str, list[str]]", self._body()["headers"]).items()}


def assert_that(actual: object) -> HttpbinAssertions:
    """Local replacement for assertpy.assert_that with project-specific matchers."""
    return HttpbinAssertions(actual)


def _read_field(body: object, path: str) -> object:
    value = body
    for key in path.split("."):
        value = cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None

    return value
