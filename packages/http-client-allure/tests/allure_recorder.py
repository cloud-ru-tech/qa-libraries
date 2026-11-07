from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from allure_commons.types import AttachmentType

REQUEST_ATTACHMENT_NAMES = ("Request details", "Request curl")
RESPONSE_CONTENT_ATTACHMENT_NAME = "Response content"
RESPONSE_HEADERS_ATTACHMENT_PREFIX = "Response headers"


@dataclass(slots=True)
class RecordedAttachment:
    name: str
    body: str
    type: AttachmentType


@dataclass(slots=True)
class RecordedStep:
    title: str
    attachments: list[RecordedAttachment] = field(default_factory=list)
    failure: str | None = None


@dataclass(slots=True)
class Report:
    """Фейк Allure: запоминает шаги и вложения вместо записи в отчет."""

    steps: list[RecordedStep] = field(default_factory=list)
    orphan_attachments: list[RecordedAttachment] = field(default_factory=list)
    _opened: list[RecordedStep] = field(default_factory=list, init=False)

    @contextmanager
    def step(self, title: str) -> Iterator[RecordedStep]:
        recorded = RecordedStep(title)
        self.steps.append(recorded)
        self._opened.append(recorded)
        try:
            yield recorded
        except BaseException as exc:
            # Allure помечает шаг упавшим только если исключение прошло через его контекст
            recorded.failure = type(exc).__name__
            raise
        finally:
            self._opened.pop()

    def attach(self, name: str, body: str, attachment_type: AttachmentType) -> None:
        recorded = RecordedAttachment(name, body, attachment_type)
        if self._opened:
            self._opened[-1].attachments.append(recorded)
        else:
            self.orphan_attachments.append(recorded)

    @property
    def attachments(self) -> list[RecordedAttachment]:
        return [attachment for step in self.steps for attachment in step.attachments]

    @property
    def request_attachment(self) -> RecordedAttachment:
        return self._only(lambda a: a.name in REQUEST_ATTACHMENT_NAMES, "запроса")

    @property
    def response_attachment(self) -> RecordedAttachment:
        return self._only(lambda a: a.name == RESPONSE_CONTENT_ATTACHMENT_NAME, "с телом ответа")

    @property
    def response_headers_attachment(self) -> RecordedAttachment:
        return self._only(lambda a: a.name.startswith(RESPONSE_HEADERS_ATTACHMENT_PREFIX), "с заголовками ответа")

    def _only(self, predicate: Callable[[RecordedAttachment], bool], kind: str) -> RecordedAttachment:
        found = [attachment for attachment in self.attachments if predicate(attachment)]
        if len(found) != 1:
            names = [attachment.name for attachment in self.attachments]
            msg = f"Ожидалось ровно одно вложение {kind}, найдено {len(found)} среди {names}"
            raise AssertionError(msg)

        return found[0]
