"""Матчеры для тестов повторных попыток.

Прячут механику проверок (разбор логов, распаковку RetryError, подсчёт попыток),
чтобы тело теста говорило только о том, какое поведение ожидается.
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
    """Проверки поведения повторных попыток."""

    def made_attempts(self, expected: int) -> Self:
        """Проверить, сколько запросов реально ушло в транспорт."""
        actual = len(self._requests())
        if actual != expected:
            self.error(f"Expected <{expected}> HTTP attempt(s), but was <{actual}>")

        return self

    def requested_path(self, expected: str) -> Self:
        """Проверить, что все попытки ушли на один и тот же путь."""
        paths = {request.url.path for request in self._requests()}
        if paths != {expected}:
            self.error(f"Expected every attempt to hit <{expected}>, but paths were <{sorted(paths)}>")

        return self

    def is_same_across_attempts(self) -> Self:
        """Проверить, что снятые в момент отправки значения совпали на всех попытках."""
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
        """Проверить, что RetryError сохранил исходную ошибку последней попытки."""
        error = self.val
        if not isinstance(error, RetryError):
            self.error(f"Expected <RetryError>, but was <{type(error).__name__}>")

        actual = cast("RetryError", error).last_attempt.exception()
        if not isinstance(actual, expected):
            self.error(f"Expected RetryError to wrap <{expected.__name__}>, but wrapped <{type(actual).__name__}>")

        return self

    def returned_response(self) -> Self:
        """Проверить, что RetryError сохранил ответ последней попытки, а не служебный объект."""
        error = self.val
        if not isinstance(error, RetryError):
            self.error(f"Expected <RetryError>, but was <{type(error).__name__}>")

        result = cast("object", cast("RetryError", error).last_attempt.result())
        if not is_http_response(result):
            self.error(f"Expected RetryError to keep an <httpx.Response>, but kept <{type(result).__name__}>")

        return self

    def logged_retry_of(self, method: str, url: str) -> Self:
        """Проверить, что среди записей лога есть повтор указанного запроса."""
        expected = f"Failed http request [{method}] {url}"
        if not any(expected in message for message in self._messages()):
            self.error(f"Expected a log record containing <{expected}>, but records were <{self._messages()}>")

        return self

    def logged_error(self, expected: str) -> Self:
        """Проверить, что в логе повтора названа причина."""
        if not any(expected in message for message in self._messages()):
            self.error(f"Expected a log record mentioning <{expected}>, but records were <{self._messages()}>")

        return self

    def _requests(self) -> list[httpx.Request]:
        return list(cast("HTTPXMock", self.val).get_requests())

    def _messages(self) -> list[str]:
        return [record.getMessage() for record in cast("Sequence[logging.LogRecord]", self.val)]


def assert_that(actual: object) -> RetryAssertions:
    """Локальная замена assertpy.assert_that с матчерами этого проекта."""
    return RetryAssertions(actual)
