from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder

MASKED_VALUE = "****"


if TYPE_CHECKING:
    from .fakes import LogEntry
    from .json_types import JsonValue

    _Builder = AssertionBuilder[object]
else:
    _Builder = AssertionBuilder


class LogEntryAssertions(_Builder):
    """Assertions for a structured HTTP client log record."""

    def has_event(self, expected: str) -> Self:
        actual = self._entry().event
        if actual != expected:
            self.error(f"Expected log event <{expected}>, but was <{actual}>")
        return self

    def has_level(self, expected: int) -> Self:
        actual = self._entry().level
        if actual != expected:
            self.error(f"Expected log level <{expected}>, but was <{actual}>")
        return self

    def has_fields(self, *expected: str) -> Self:
        actual = set(self._entry().params)
        if actual != set(expected):
            self.error(f"Expected log entry fields <{sorted(expected)}>, but were <{sorted(actual)}>")
        return self

    def has_no_field(self, name: str) -> Self:
        params = self._entry().params
        if name in params:
            self.error(f"Expected no field <{name}>, but it held <{params[name]}>")
        return self

    def has_field(self, name: str, expected: object) -> Self:
        return self._has_param(name, expected)

    def has_method(self, expected: str) -> Self:
        return self._has_param("method", expected)

    def has_url(self, expected: str) -> Self:
        return self._has_param("url", expected)

    def has_status_code(self, expected: int) -> Self:
        return self._has_param("status_code", expected)

    def has_body(self, expected: str) -> Self:
        return self._has_param("body", expected)

    def has_body_containing(self, expected: str) -> Self:
        actual = str(self._param("body"))
        if expected not in actual:
            self.error(f"Expected body to contain <{expected}>, but was <{actual}>")
        return self

    def has_body_of_length(self, expected: int) -> Self:
        actual = len(str(self._param("body")))
        if actual != expected:
            self.error(f"Expected body of <{expected}> characters, but was <{actual}>")
        return self

    def has_trace_id(self) -> Self:
        trace_id = self._param("trace_id")
        if not trace_id:
            self.error(f"Expected a non-empty trace_id, but was <{trace_id}>")
        return self

    def has_same_trace_id_as(self, other: LogEntry) -> Self:
        actual = self._param("trace_id")
        expected = other.params.get("trace_id")
        if actual != expected:
            self.error(f"Expected trace_id <{expected}> linking the entries, but was <{actual}>")
        return self

    def has_header(self, name: str, expected: str) -> Self:
        return self._has_json_entry("headers", name, expected)

    def has_masked_header(self, name: str) -> Self:
        return self._has_json_entry("headers", name, MASKED_VALUE)

    def has_query_param(self, name: str, expected: str) -> Self:
        return self._has_json_entry("query_params", name, expected)

    def has_body_field(self, name: str, expected: object) -> Self:
        return self._has_json_entry("body", name, expected)

    def has_masked_body_field(self, name: str) -> Self:
        return self._has_json_entry("body", name, MASKED_VALUE)

    def does_not_expose(self, secret: str) -> Self:
        leaking = [name for name, value in self._entry().params.items() if secret in str(value)]
        if leaking:
            self.error(f"Expected <{secret}> to stay hidden, but it leaked into <{sorted(leaking)}>")
        return self

    def _entry(self) -> LogEntry:
        return cast("LogEntry", self.val)

    def _param(self, name: str) -> object:
        params = self._entry().params
        if name not in params:
            self.error(f"Expected field <{name}>, but entry had <{sorted(params)}>")
        return params[name]

    def _has_param(self, name: str, expected: object) -> Self:
        actual = self._param(name)
        if actual != expected:
            self.error(f"Expected field <{name}> to be <{expected}>, but was <{actual}>")
        return self

    def _has_json_entry(self, part: str, name: str, expected: object) -> Self:
        parsed = self._parse_json_param(part)
        if name not in parsed:
            self.error(f"Expected <{part}> to hold <{name}>, but held <{sorted(parsed)}>")
        if parsed[name] != expected:
            self.error(f"Expected <{part}.{name}> to be <{expected}>, but was <{parsed[name]}>")
        return self

    def _parse_json_param(self, part: str) -> dict[str, JsonValue]:
        raw = self._param(part)
        try:
            return cast("dict[str, JsonValue]", json.loads(cast("str", raw)))
        except (TypeError, json.JSONDecodeError):
            self.error(f"Expected <{part}> to hold JSON, but was <{raw}>")
            raise


def assert_that(val: object, description: str = "") -> LogEntryAssertions:
    """Start assertions for either log records or ordinary values."""
    return LogEntryAssertions(val, description)
