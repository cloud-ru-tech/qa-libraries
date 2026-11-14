"""Matchers for retry tests.

Hide assertion mechanics (log parsing, RetryError unpacking, attempt counting)
so the test body describes only the expected behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder
from http_client_retries._types import is_http_response
from tenacity import RetryError

if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence

    import httpx
    from pytest_httpx import HTTPXMock

    _Assertions = AssertionBuilder[object]
else:
    _Assertions = AssertionBuilder


class RetryAssertions(_Assertions):
    """Assertions for retry behavior."""

    def made_attempts(self, expected: int) -> Self:
        """Check the number of requests actually sent to the transport."""
        actual = len(self._requests())
        if actual != expected:
            self.error(f"Expected <{expected}> HTTP attempt(s), but was <{actual}>")

        return self

    def requested_path(self, expected: str) -> Self:
        """Check that all attempts were sent to the same path."""
        paths = {request.url.path for request in self._requests()}
        if paths != {expected}:
            self.error(f"Expected every attempt to hit <{expected}>, but paths were <{sorted(paths)}>")

        return self

    def is_same_across_attempts(self) -> Self:
        """Check that values captured at send time match across all attempts."""
        values: list[str | None] = list(cast("Sequence[str | None]", self.val))
        minimum_attempts = 2
        if len(values) < minimum_attempts:
            self.error(f"Expected at least two attempts to compare, but captured <{values}>")

        if None in values:
            self.error(f"Expected every attempt to carry the header, but captured <{values}>")

        if len(set(values)) != 1:
            self.error(f"Expected one value across all attempts, but captured <{values}>")

        return self

    def wraps_error(self, expected: type[BaseException]) -> Self:
        """Check that RetryError retains the original error from the last attempt."""
        error = self.val
        if not isinstance(error, RetryError):
            self.error(f"Expected <RetryError>, but was <{type(error).__name__}>")

        actual = cast("RetryError", error).last_attempt.exception()
        if not isinstance(actual, expected):
            self.error(f"Expected RetryError to wrap <{expected.__name__}>, but wrapped <{type(actual).__name__}>")

        return self

    def returned_response(self) -> Self:
        """Check that RetryError retains the last response rather than an internal object."""
        error = self.val
        if not isinstance(error, RetryError):
            self.error(f"Expected <RetryError>, but was <{type(error).__name__}>")

        result = cast("object", cast("RetryError", error).last_attempt.result())
        if not is_http_response(result):
            self.error(f"Expected RetryError to keep an <httpx.Response>, but kept <{type(result).__name__}>")

        return self

    def logged_retry_of(self, method: str, url: str) -> Self:
        """Check that the logs contain a retry of the specified request."""
        expected = f"Failed http request [{method}] {url}"
        if not any(expected in message for message in self._messages()):
            self.error(f"Expected a log record containing <{expected}>, but records were <{self._messages()}>")

        return self

    def logged_error(self, expected: str) -> Self:
        """Check that the retry log names the reason."""
        if not any(expected in message for message in self._messages()):
            self.error(f"Expected a log record mentioning <{expected}>, but records were <{self._messages()}>")

        return self

    def _requests(self) -> list[httpx.Request]:
        return list(cast("HTTPXMock", self.val).get_requests())

    def _messages(self) -> list[str]:
        return [record.getMessage() for record in cast("Sequence[logging.LogRecord]", self.val)]


def assert_that(actual: object) -> RetryAssertions:
    """Local replacement for assertpy.assert_that with project-specific matchers."""
    return RetryAssertions(actual)
