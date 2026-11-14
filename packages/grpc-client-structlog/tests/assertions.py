from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder
from grpc_client.utils.logutils import TRUNCATION_SUFFIX

MASKED_VALUE = "****"


if TYPE_CHECKING:
    from .fakes import LogEntry

    _Builder = AssertionBuilder[object]
else:
    _Builder = AssertionBuilder


class LogEntryAssertions(_Builder):
    """Assertions for structured gRPC client log records."""

    def has_event(self, expected: str) -> Self:
        """Check the record event name."""
        actual = self._entry().event
        if actual != expected:
            self.error(f"Ожидалось событие лога <{expected}>, а было <{actual}>")
        return self

    def has_level(self, expected: int) -> Self:
        """Check the record level."""
        actual = self._entry().level
        if actual != expected:
            self.error(f"Ожидался уровень лога <{expected}>, а был <{actual}>")
        return self

    def has_fields(self, *expected: str) -> Self:
        """Check the complete set of record fields."""
        actual = set(self._entry().params)
        if actual != set(expected):
            self.error(f"Ожидались поля записи <{sorted(expected)}>, а были <{sorted(actual)}>")
        return self

    def has_no_field(self, name: str) -> Self:
        """Check whether a field is absent from the record."""
        params = self._entry().params
        if name in params:
            self.error(f"Поля <{name}> не должно быть в записи, а в нем было <{params[name]}>")
        return self

    def has_method(self, expected: str) -> Self:
        """Check the called method name."""
        return self._has_param("method", expected)

    def has_status_code(self, expected: str) -> Self:
        """Check the response status code."""
        return self._has_param("status_code", expected)

    def has_details(self, expected: str) -> Self:
        """Check the service error text."""
        return self._has_param("details", expected)

    def has_messages_count(self, expected: int) -> Self:
        """Check the number of received stream messages."""
        return self._has_param("messages_count", expected)

    def has_body(self, expected: str) -> Self:
        """Check the entire message body."""
        return self._has_param("body", expected)

    def has_truncated_body(self, maxlength: int) -> Self:
        """Check whether the message body is truncated to the specified length."""
        actual = str(self._param("body"))
        expected_length = maxlength + len(TRUNCATION_SUFFIX)
        if not actual.endswith(TRUNCATION_SUFFIX) or len(actual) != expected_length:
            self.error(f"Ожидалось тело длиной <{expected_length}> с пометкой об обрезке, а было <{actual}>")
        return self

    def has_body_field(self, name: str, expected: object) -> Self:
        """Check a field value in the message body."""
        return self._has_json_entry("body", name, expected)

    def has_masked_body_field(self, name: str) -> Self:
        """Check whether a message body field value is hidden."""
        return self._has_json_entry("body", name, MASKED_VALUE)

    def has_metadata_value(self, name: str, expected: object) -> Self:
        """Check a metadata key value."""
        return self._has_json_entry("metadata", name, expected)

    def has_masked_metadata_value(self, name: str) -> Self:
        """Check whether a metadata key value is hidden."""
        return self._has_json_entry("metadata", name, MASKED_VALUE)

    def has_trace_id(self) -> Self:
        """Check whether a record has a nonempty identifier."""
        trace_id = self._param("trace_id")
        if not trace_id:
            self.error(f"Ожидался непустой trace_id, а был <{trace_id}>")
        return self

    def has_same_trace_id_as(self, other: LogEntry) -> Self:
        """Check whether two records share an identifier."""
        actual = self._param("trace_id")
        expected = other.params.get("trace_id")
        if actual != expected:
            self.error(f"Ожидался связывающий записи trace_id <{expected}>, а был <{actual}>")
        return self

    def does_not_expose(self, secret: str) -> Self:
        """Check whether a secret is absent from every record field."""
        leaking = [name for name, value in self._entry().params.items() if secret in str(value)]
        if leaking:
            self.error(f"Значение <{secret}> должно быть скрыто, а оно утекло в поля <{sorted(leaking)}>")
        return self

    def _entry(self) -> LogEntry:
        return cast("LogEntry", self.val)

    def _param(self, name: str) -> object:
        params = self._entry().params
        if name not in params:
            self.error(f"Ожидалось поле <{name}>, а в записи были <{sorted(params)}>")
        return params[name]

    def _has_param(self, name: str, expected: object) -> Self:
        actual = self._param(name)
        if actual != expected:
            self.error(f"Ожидалось поле <{name}> со значением <{expected}>, а было <{actual}>")
        return self

    def _has_json_entry(self, part: str, name: str, expected: object) -> Self:
        parsed = self._parse_json_param(part)
        if name not in parsed:
            self.error(f"Ожидался ключ <{name}> в поле <{part}>, а были <{sorted(parsed)}>")
        if parsed[name] != expected:
            self.error(f"Ожидалось <{part}.{name}> со значением <{expected}>, а было <{parsed[name]}>")
        return self

    def _parse_json_param(self, part: str) -> dict[str, object]:
        raw = self._param(part)
        try:
            return cast("dict[str, object]", json.loads(cast("str", raw)))
        except (TypeError, json.JSONDecodeError):
            self.error(f"Ожидался JSON в поле <{part}>, а было <{raw}>")
            raise


def assert_that(val: object, description: str = "") -> LogEntryAssertions:
    """Start assertions supporting both log records and ordinary values.

    :param val: value to check
    :param description: description inserted into the error message
    :returns: assertion builder
    """
    return LogEntryAssertions(val, description)
