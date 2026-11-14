from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder
from pytest_httpx import HTTPXMock

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx

    _Assertions = AssertionBuilder[object]
else:
    _Assertions = AssertionBuilder


class HttpxMockAssertions(_Assertions):
    """Assertions for requests captured by pytest-httpx."""

    def sent_json_to(self, path: str, expected: Mapping[str, object]) -> Self:
        """Check that a request to the path has the expected JSON body.

        :param path: Request path without the scheme and host
        :param expected: Expected request body
        :return: Assertion builder for continuing the chain
        """
        bodies = [cast("object", json.loads(request.content)) for request in self._requests_to(path)]
        if expected not in bodies:
            self.error(f"Ожидался запрос на <{path}> с телом <{expected}>, а отправлены были <{bodies}>")
        return self

    def sent_bearer_token_to(self, path: str, expected: str) -> Self:
        """Check that a request to the path has the specified token in its Authorization header.

        :param path: Request path without the scheme and host
        :param expected: Expected access token value
        :return: Assertion builder for continuing the chain
        """
        tokens = [cast("str | None", request.headers.get("Authorization")) for request in self._requests_to(path)]
        if f"Bearer {expected}" not in tokens:
            self.error(f"Ожидался запрос на <{path}> с токеном <{expected}>, а отправлены были <{tokens}>")
        return self

    def sent_requests_to(self, path: str, expected_count: int) -> Self:
        """Check the number of requests sent to a path.

        :param path: Request path without the scheme and host
        :param expected_count: Expected request count
        :return: Assertion builder for continuing the chain
        """
        actual_count = len(self._requests_to(path))
        if actual_count != expected_count:
            self.error(f"Ожидалось запросов на <{path}>: <{expected_count}>, а отправлено было <{actual_count}>")
        return self

    def _requests_to(self, path: str) -> list[httpx.Request]:
        if not isinstance(self.val, HTTPXMock):
            message = "Утверждение применимо только к HTTPXMock"
            raise TypeError(message)

        return [request for request in self.val.get_requests() if request.url.path == path]


def assert_that(val: object, description: str = "") -> HttpxMockAssertions:
    """Start an assertion chain with HTTP request assertions.

    :param val: Value to check
    :param description: Description included in the error message
    :return: Assertion builder
    """
    return HttpxMockAssertions(val, description)
