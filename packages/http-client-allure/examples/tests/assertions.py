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
    """Проверки ответов httpbin.

    Прячут разбор эха httpbin и распаковку RetryError, чтобы тело теста
    говорило только о том, какое поведение ожидается.
    """

    def has_status(self, expected: int) -> Self:
        """Проверить код ответа."""
        actual = cast("httpx.Response", self.val).status_code
        if actual != expected:
            self.error(f"Expected status <{expected}>, but was <{actual}>")

        return self

    def has_text(self, expected: str) -> Self:
        """Проверить текстовое тело ответа."""
        actual = cast("httpx.Response", self.val).text
        if actual != expected:
            self.error(f"Expected body <{expected}>, but was <{actual}>")

        return self

    def has_empty_body(self) -> Self:
        """Проверить, что тело ответа пустое."""
        actual = cast("httpx.Response", self.val).content
        if actual:
            self.error(f"Expected an empty body, but was <{actual!r}>")

        return self

    def has_response_header(self, name: str, expected: str) -> Self:
        """Проверить заголовок, который вернул сервер."""
        actual = cast("str | None", cast("httpx.Response", self.val).headers.get(name))
        if actual != expected:
            self.error(f"Expected response header <{name}> to be <{expected}>, but was <{actual}>")

        return self

    def hits_path(self, expected: str) -> Self:
        """Проверить путь, на котором запрос остановился после редиректов."""
        actual = cast("httpx.Response", self.val).url.path
        if actual != expected:
            self.error(f"Expected the request to land on <{expected}>, but landed on <{actual}>")

        return self

    def has_json_field(self, path: str, *, expected: object) -> Self:
        """Проверить поле тела ответа по точечному пути."""
        actual = _read_field(self._body(), path)
        if actual != expected:
            self.error(f"Expected field <{path}> to be <{expected}>, but was <{actual}>")

        return self

    def have_distinct_json_field(self, path: str) -> Self:
        """Проверить, что каждый ответ списка принес свое значение поля."""
        values = [
            _read_field(cast("object", response.json()), path) for response in cast("list[httpx.Response]", self.val)
        ]
        if len(set(values)) != len(values):
            self.error(f"Expected every response to carry its own <{path}>, but was <{values}>")

        return self

    def echoes_json(self, expected: object) -> Self:
        """Проверить JSON тело запроса, которое httpbin вернул обратно."""
        actual = self._body()["json"]
        if actual != expected:
            self.error(f"Expected httpbin to echo <{expected}>, but echoed <{actual}>")

        return self

    def echoes_body(self, expected: str) -> Self:
        """Проверить сырое тело запроса, которое httpbin вернул обратно."""
        actual = self._body()["data"]
        if actual != expected:
            self.error(f"Expected httpbin to echo <{expected}>, but echoed <{actual}>")

        return self

    def echoes_query_param(self, name: str, expected: list[str]) -> Self:
        """Проверить query параметр, дошедший до сервера."""
        actual = cast("dict[str, list[str]]", self._body()["args"]).get(name)
        if actual != expected:
            self.error(f"Expected query parameter <{name}> to be <{expected}>, but was <{actual}>")

        return self

    def echoes_header(self, name: str, expected: list[str]) -> Self:
        """Проверить заголовок, дошедший до сервера."""
        actual = self._headers().get(name.lower())
        if actual != expected:
            self.error(f"Expected header <{name}> to be <{expected}>, but was <{actual}>")

        return self

    def carries_header(self, name: str) -> Self:
        """Проверить, что заголовок дошел до сервера с непустым значением."""
        actual = self._headers().get(name.lower())
        if not actual or not all(actual):
            self.error(f"Expected header <{name}> to carry a value, but was <{actual}>")

        return self

    def kept_response_with_status(self, expected: int) -> Self:
        """Проверить ответ последней попытки, сохраненный в RetryError."""
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
    """Локальная замена assertpy.assert_that с матчерами этого проекта."""
    return HttpbinAssertions(actual)


def _read_field(body: object, path: str) -> object:
    value = body
    for key in path.split("."):
        value = cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None

    return value
