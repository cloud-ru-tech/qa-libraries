from collections.abc import Iterable, Iterator, Mapping
from typing import cast

from .types import MetadataItems, MetadataType, MetadataValue


def as_metadata_items(metadata: MetadataType | None) -> MetadataItems:
    """Normalize metadata to a sequence of pairs.

    :param metadata: metadata in any supported form
    :return: sequence of key-value pairs
    """
    if metadata is None:
        return ()
    if isinstance(metadata, Metadata):
        return metadata.pairs()
    if isinstance(metadata, Mapping):
        return tuple(metadata.items())
    return tuple(metadata)


def aio_metadata_items(metadata: object) -> MetadataItems:
    """Normalize asynchronous call metadata to a sequence of pairs.

    `grpc.aio` has its own metadata type: it iterates over pairs but is not a Sequence.

    :param metadata: asynchronous call metadata
    :return: sequence of key-value pairs
    """
    if metadata is None:
        return ()
    return tuple(cast("Iterable[tuple[str, MetadataValue]]", metadata))


def merge_metadata(*sources: MetadataType | None) -> MetadataItems:
    """Merge metadata from multiple sources while preserving order.

    :param sources: metadata sets, each appended after the previous one
    :return: sequence of key-value pairs
    """
    merged: list[tuple[str, MetadataValue]] = []
    for source in sources:
        merged.extend(as_metadata_items(source))
    return tuple(merged)


def contains_key(metadata: MetadataType | None, key: str) -> bool:
    """Check whether metadata contains a key, ignoring case.

    :param metadata: request metadata
    :param key: key to find
    :return: True if the key is present
    """
    normalized = key.lower()
    return any(name.lower() == normalized for name, _ in as_metadata_items(metadata))


class Metadata(Mapping[str, MetadataValue]):
    """gRPC metadata that preserves order and repeated keys.

    Behaves like a dictionary: key access returns the first value. All values are available through `get_all()`.
    Keys are compared case-insensitively as required by HTTP/2.
    """

    __slots__ = ("_items",)

    def __init__(self, metadata: MetadataType | None = None) -> None:
        """Create an instance with the supplied settings."""
        self._items: tuple[tuple[str, MetadataValue], ...] = tuple(as_metadata_items(metadata))

    def __getitem__(self, key: str) -> MetadataValue:
        """Return the first value of a metadata key."""
        normalized = key.lower()
        for name, value in self._items:
            if name.lower() == normalized:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Get an iterator of values."""
        seen: set[str] = set()
        for name, _ in self._items:
            normalized = name.lower()
            if normalized not in seen:
                seen.add(normalized)
                yield name

    def __len__(self) -> int:
        """Get the number of unique metadata keys."""
        return sum(1 for _ in iter(self))

    def __repr__(self) -> str:
        """Return the string representation of metadata."""
        return f"{type(self).__name__}({list(self._items)!r})"

    def get_all(self, key: str) -> tuple[MetadataValue, ...]:
        """Get all values for a key.

        :param key: metadata key name
        :return: values in arrival order, or an empty tuple if the key is absent
        """
        normalized = key.lower()
        return tuple(value for name, value in self._items if name.lower() == normalized)

    def pairs(self) -> tuple[tuple[str, MetadataValue], ...]:
        """Get all key-value pairs, including repeated keys.

        Unlike `items()`, this preserves all values of repeated keys.
        """
        return self._items
