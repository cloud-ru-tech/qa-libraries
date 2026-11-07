from dataclasses import dataclass, replace

import allure
from allure_commons.types import AttachmentType


@dataclass(frozen=True, slots=True)
class Attachment:
    """Данные для прикрепления к allure шагу."""

    name: str
    content: str
    type: AttachmentType

    def truncate(self, max_length: int | None) -> "Attachment":
        """Вернуть копию с содержимым, обрезанным до max_length.

        Обрезанный JSON перестает быть валидным, поэтому у обрезанного вложения
        тип понижается до TEXT — иначе Allure не сможет его отрисовать.

        :param max_length: максимальная длина содержимого, если None - обрезка не выполняется
        :return: исходное вложение либо его обрезанная копия
        """
        if max_length is None or len(self.content) <= max_length:
            return self

        suffix = f"\n\n... (обрезано, полная длина: {len(self.content)} символов)"
        return replace(
            self,
            content=self.content[:max_length] + suffix,
            type=allure.attachment_type.TEXT,
        )

    def attach(self) -> None:
        """Прикрепить вложение к текущему allure шагу."""
        allure.attach(name=self.name, body=self.content, attachment_type=self.type)
