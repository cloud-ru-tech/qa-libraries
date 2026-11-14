"""HTTP client log capture and assertion matchers."""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from assertpy.assertpy import AssertionBuilder

TRACE_ID = re.compile(r"id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")

# Log sections have a fixed order: each value extends to the next section label.
PART_ORDER = ("Request", "Response", "Method", "Status", "QueryParams", "Headers", "Body")


@dataclass(frozen=True)
class LogEntry:
    """Single HTTP client log record."""

    level: int
    message: str

    def part(self, name: str) -> str | None:
        """Value of a log section by its label, or None if it is absent."""
        marker = f"{name}: "
        start = self.message.find(marker)
        if start < 0:
            return None

        value_at = start + len(marker)
        following = [
            position
            for other in PART_ORDER[PART_ORDER.index(name) + 1 :]
            if (position := self.message.find(f"{other}: ", value_at)) >= 0
        ]
        return self.message[value_at : min(following, default=len(self.message))].rstrip("\n ")

    def trace_id(self) -> str | None:
        """ID correlating the request and response logs."""
        found = TRACE_ID.search(self.message)
        return found.group(1) if found else None


class RecordingHandler(logging.Handler):
    """Handler that stores records in memory instead of displaying them."""

    def __init__(self) -> None:
        """Create a handler with an empty record list."""
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@dataclass(frozen=True)
class RecordedLog:
    """Real logger with captured records: a fake rather than a mock.

    The client writes two records per HTTP exchange: the request, then the response.
    """

    logger: logging.Logger
    handler: RecordingHandler

    @property
    def entries(self) -> list[LogEntry]:
        return [LogEntry(level=record.levelno, message=record.getMessage()) for record in self.handler.records]

    @property
    def request(self) -> LogEntry:
        return self._entry(index=0, what="запросе")

    @property
    def response(self) -> LogEntry:
        return self._entry(index=1, what="ответе")

    def _entry(self, index: int, what: str) -> LogEntry:
        entries = self.entries
        if index >= len(entries):
            message = f"Ожидалась запись о {what}, но логгер получил только {len(entries)} записей"
            raise AssertionError(message)
        return entries[index]


if TYPE_CHECKING:
    _LogEntryAssertions = AssertionBuilder[LogEntry]
else:
    _LogEntryAssertions = AssertionBuilder


class LogAssertions(_LogEntryAssertions):
    """Check an HTTP client log record."""

    def has_trace_id(self) -> Self:
        if self.val.trace_id() is None:
            self.error(f"Ожидался идентификатор обмена вида id=<uuid>, но лог его не содержит: <{self.val.message}>")
        return self

    def has_same_trace_id_as(self, other: LogEntry) -> Self:
        expected = other.trace_id()
        actual = self.val.trace_id()
        if actual is None or actual != expected:
            self.error(f"Ожидался идентификатор обмена <{expected}>, но был <{actual}>")
        return self

    def describes_request(self, method: str, url: str) -> Self:
        return self._part_equals("Method", f"[{method}] {url}")

    def describes_response(self, status: int, reason: str) -> Self:
        return self._part_equals("Status", f"{status} [{reason}]")

    def has_header(self, name: str, value: str) -> Self:
        return self._part_contains("Headers", f'"{name}": "{value}"')

    def has_query_param(self, name: str, value: str) -> Self:
        return self._part_contains("QueryParams", f'"{name}": "{value}"')

    def has_body(self, expected: str) -> Self:
        return self._part_equals("Body", expected)

    def has_no_body(self) -> Self:
        actual = self.val.part("Body")
        if actual is not None:
            self.error(f"Ожидалось, что тело в лог не попадёт, но было записано <{actual}>")
        return self

    def has_body_matching(self, pattern: str) -> Self:
        actual = self._body()
        if not re.fullmatch(pattern, actual, flags=re.DOTALL):
            self.error(f"Ожидалось тело по шаблону <{pattern}>, но было <{actual}>")
        return self

    def has_body_no_longer_than(self, limit: int) -> Self:
        actual = self._body()
        if len(actual) > limit:
            self.error(f"Ожидалось тело не длиннее <{limit}> символов, но было <{len(actual)}>: <{actual}>")
        return self

    def hides(self, secret: str) -> Self:
        if secret in self.val.message:
            self.error(f"Ожидалось, что <{secret}> не попадёт в лог, но лог его содержит: <{self.val.message}>")
        return self

    def reveals(self, text: str) -> Self:
        if text not in self.val.message:
            self.error(f"Ожидалось, что лог содержит <{text}>, но лог был <{self.val.message}>")
        return self

    def logged_at(self, level: int) -> Self:
        if self.val.level != level:
            self.error(
                f"Ожидался уровень <{logging.getLevelName(level)}>, но был <{logging.getLevelName(self.val.level)}>"
            )
        return self

    def _part_equals(self, name: str, expected: str) -> Self:
        actual = self.val.part(name)
        if actual != expected:
            self.error(f"Ожидалась часть лога {name} равная <{expected}>, но была <{actual}>")
        return self

    def _part_contains(self, name: str, expected: str) -> Self:
        actual = self.val.part(name)
        if actual is None or expected not in actual:
            self.error(f"Ожидалось, что часть лога {name} содержит <{expected}>, но она была <{actual}>")
        return self

    def _body(self) -> str:
        actual = self.val.part("Body")
        if actual is None:
            self.error(f"Ожидалось тело в логе, но его там нет: <{self.val.message}>")
        return actual or ""


def assert_that(value: LogEntry) -> LogAssertions:
    """Check an HTTP client log record."""
    return LogAssertions(value)
