"""Matchers for data chunks read from a streaming response."""

from typing import TYPE_CHECKING, Self

from assertpy.assertpy import AssertionBuilder

if TYPE_CHECKING:
    _ChunkListAssertions = AssertionBuilder[list[bytes]]
else:
    _ChunkListAssertions = AssertionBuilder


class ChunksAssertions(_ChunkListAssertions):
    """Check a sequence of streaming response chunks."""

    def are_no_longer_than(self, limit: int) -> Self:
        too_long = [len(chunk) for chunk in self.val if len(chunk) > limit]
        if too_long:
            self.error(f"Ожидались порции не длиннее <{limit}> байт, но пришли порции размером <{too_long}>")
        return self

    def join_to(self, expected: bytes) -> Self:
        actual = b"".join(self.val)
        if actual != expected:
            self.error(f"Ожидалось, что порции сложатся в <{expected!r}>, но сложились в <{actual!r}>")
        return self

    def are_split_in_more_than_one(self) -> Self:
        if len(self.val) <= 1:
            self.error(f"Ожидалось разбиение на несколько порций, но пришла <{len(self.val)}>")
        return self


def assert_chunks(chunks: list[bytes]) -> ChunksAssertions:
    """Check a sequence of streaming response chunks."""
    return ChunksAssertions(chunks)
