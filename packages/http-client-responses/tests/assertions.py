from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder

if TYPE_CHECKING:
    from http_client_responses import ResponseParseError

    from .models import ExampleResponse

    _Assertions = AssertionBuilder[object]
else:
    _Assertions = AssertionBuilder


class ResponseAssertions(_Assertions):
    """Проверки для разобранных моделей ответа и для ошибок разбора."""

    def has_user_names(self, expected: list[str]) -> Self:
        actual = [user.name for user in cast("ExampleResponse", self.val).users]
        if actual != expected:
            self.error(f"Expected users named <{expected}>, but was <{actual}>")
        return self

    def has_skills(self, expected: dict[str, list[str]]) -> Self:
        actual = {user.name: user.skills for user in cast("ExampleResponse", self.val).users}
        if actual != expected:
            self.error(f"Expected skills <{expected}>, but was <{actual}>")
        return self

    def reports_request(self, method: str, url: str, status_code: int) -> Self:
        expected_line = f"{method} {url} -> {status_code}"
        if expected_line not in self._message():
            self.error(f"Expected error to report <{expected_line}>, but message was <{self._message()}>")
        return self

    def quotes_body(self, expected: str) -> Self:
        if expected not in self._message():
            self.error(f"Expected error to quote body <{expected}>, but message was <{self._message()}>")
        return self

    def omits_body(self, unexpected: str) -> Self:
        if unexpected in self._message():
            self.error(f"Expected error to omit body of {len(unexpected)} characters, but it was quoted in full")
        return self

    def caused_by(self, expected: type[Exception]) -> Self:
        actual = cast("ResponseParseError", self.val).cause
        if not isinstance(actual, expected):
            self.error(f"Expected cause of type <{expected.__name__}>, but was <{type(actual).__name__}>")
        return self

    def _message(self) -> str:
        return str(self.val)


def assert_that(actual: object) -> ResponseAssertions:
    return ResponseAssertions(actual)
