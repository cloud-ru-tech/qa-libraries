from dataclasses import dataclass, replace

import allure
from allure_commons.types import AttachmentType


@dataclass(frozen=True, slots=True)
class Attachment:
    """Data to attach to an Allure step."""

    name: str
    content: str
    type: AttachmentType

    def truncate(self, max_length: int | None) -> "Attachment":
        """Return a copy with contents truncated to max_length.

        Truncated JSON is no longer valid, so downgrade a truncated attachment
        to TEXT; otherwise Allure cannot render it.

        :param max_length: Maximum content length; None disables truncation
        :return: Original attachment or a truncated copy
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
        """Attach data to the current Allure step."""
        allure.attach(name=self.name, body=self.content, attachment_type=self.type)
