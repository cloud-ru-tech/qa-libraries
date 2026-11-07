from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self, cast

import glom
from assertpy.assertpy import AssertionBuilder

TRUNCATION_MARKER = "обрезано, полная длина"


if TYPE_CHECKING:
    from allure_commons.types import AttachmentType

    from .allure_recorder import RecordedAttachment, RecordedStep, Report

    _Builder = AssertionBuilder[object]
else:
    _Builder = AssertionBuilder


class ReportAssertions(_Builder):
    """Проверки записанного Allure отчета."""

    def has_single_step(self, expected_title: str) -> Self:
        titles = [step.title for step in self._report().steps]
        if titles != [expected_title]:
            self.error(f"Ожидался один шаг <{expected_title}>, записаны шаги <{titles}>")

        return self

    def has_attachment_names(self, expected: list[str]) -> Self:
        names = [attachment.name for attachment in self._report().attachments]
        if names != expected:
            self.error(f"Ожидались вложения <{expected}>, записаны <{names}>")

        return self

    def has_attachments_count(self, expected: int) -> Self:
        names = [attachment.name for attachment in self._report().attachments]
        if len(names) != expected:
            self.error(f"Ожидалось вложений: <{expected}>, записано <{len(names)}>: <{names}>")

        return self

    def has_failed_step(self, expected_title: str) -> Self:
        step = self._step(expected_title)
        if step.failure is None:
            self.error(f"Шаг <{expected_title}> закрыт как успешный, ожидалась ошибка")

        return self

    def has_passed_step(self, expected_title: str) -> Self:
        step = self._step(expected_title)
        if step.failure is not None:
            self.error(f"Шаг <{expected_title}> помечен упавшим из-за <{step.failure}>")

        return self

    def has_every_attachment_inside_step(self) -> Self:
        orphans = [attachment.name for attachment in self._report().orphan_attachments]
        if orphans:
            self.error(f"Вложения <{orphans}> прикреплены вне шага")

        return self

    def _report(self) -> Report:
        return cast("Report", self.val)

    def _step(self, title: str) -> RecordedStep:
        found = [step for step in self._report().steps if step.title == title]
        if len(found) != 1:
            titles = [step.title for step in self._report().steps]
            self.error(f"Ожидался ровно один шаг <{title}>, найдено {len(found)} среди <{titles}>")

        return found[0]


class AttachmentAssertions(_Builder):
    """Проверки одного вложения Allure."""

    def has_name(self, expected: str) -> Self:
        actual = self._attachment().name
        if actual != expected:
            self.error(f"Ожидалось имя вложения <{expected}>, было <{actual}>")

        return self

    def has_body(self, expected: str) -> Self:
        actual = self._attachment().body
        if actual != expected:
            self.error(f"Ожидалось тело вложения <{expected}>, было <{actual}>")

        return self

    def has_type(self, expected: AttachmentType) -> Self:
        actual = self._attachment().type
        if actual != expected:
            self.error(f"Ожидался тип вложения <{expected}>, был <{actual}>")

        return self

    def has_json_value(self, path: str, expected: object) -> Self:
        parsed = self._parsed_body()
        actual = glom.glom(parsed, path, default=None)
        if actual != expected:
            self.error(f"Ожидалось <{path}> = <{expected}>, было <{actual}> в <{parsed}>")

        return self

    def has_json_body(self, expected: object) -> Self:
        actual = self._parsed_body()
        if actual != expected:
            self.error(f"Ожидалось тело вложения <{expected}>, было <{actual}>")

        return self

    def shows(self, fragment: str) -> Self:
        actual = self._attachment().body
        if fragment not in actual:
            self.error(f"Ожидалось вхождение <{fragment}> в <{actual}>")

        return self

    def hides(self, secret: str) -> Self:
        actual = self._attachment().body
        if secret in actual:
            self.error(f"Секрет <{secret}> не замаскирован в <{actual}>")

        return self

    def is_truncated(self) -> Self:
        actual = self._attachment().body
        if TRUNCATION_MARKER not in actual:
            self.error(f"Ожидалась пометка об обрезке в <{actual}>")

        return self

    def is_not_truncated(self) -> Self:
        actual = self._attachment().body
        if TRUNCATION_MARKER in actual:
            self.error(f"Вложение неожиданно обрезано: <{actual}>")

        return self

    def _attachment(self) -> RecordedAttachment:
        return cast("RecordedAttachment", self.val)

    def _parsed_body(self) -> object:
        body = self._attachment().body
        try:
            return cast("object", json.loads(body))
        except json.JSONDecodeError:
            self.error(f"Тело вложения не разбирается как JSON: <{body}>")
            raise


def assert_report(report: Report) -> ReportAssertions:
    return ReportAssertions(report)


def assert_attachment(attachment: RecordedAttachment) -> AttachmentAssertions:
    return AttachmentAssertions(attachment)
