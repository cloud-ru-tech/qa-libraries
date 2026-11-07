"""Response wrappers for MCP client."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from mcp.types import AudioContent, CallToolResult, EmbeddedResource, ImageContent, ResourceLink, TextContent

    type Content = TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource


class ToolCallResponse:
    """Expose content and status of an MCP tool result."""

    def __init__(self, result: CallToolResult) -> None:
        """Wrap a protocol result.

        :param result: Protocol response returned by the server.
        """
        self.result = result

    @property
    def is_success(self) -> bool:
        """Return whether the server reported success."""
        return not self.result.isError

    @property
    def is_error(self) -> bool:
        """Return whether the server reported an error."""
        return self.result.isError

    @property
    def content(self) -> list[Content]:
        """Return the response content blocks."""
        return self.result.content

    @property
    def structured_content(self) -> dict[str, object] | None:
        """Return the structured response content."""
        return cast("dict[str, object] | None", self.result.structuredContent)

    @property
    def metadata(self) -> dict[str, object] | None:
        """Return response metadata."""
        return cast("dict[str, object] | None", self.result.meta)

    def text_content(self) -> str:
        """Join text blocks in their original order."""
        return "\n".join(item.text for item in self.result.content if item.type == "text")
