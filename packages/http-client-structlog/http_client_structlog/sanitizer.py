from collections.abc import Iterable, Sequence
from typing import cast

from http_client.utils.sanitizer import sanitize

MASKED_VALUE = "****"


class Sanitizer:
    """Rules for masking sensitive data in logs.

    Exact paths and common names need different lookups. The path `user.password` selects one
    specific field, while `password` from the common secrets list must match at any
    depth: secrets are equally sensitive at the body root and in nested objects.
    """

    def __init__(
        self,
        glom_paths: Sequence[str] = (),
        secret_names: Iterable[str] = (),
    ) -> None:
        """Create an instance with the supplied settings."""
        self._glom_paths = tuple(glom_paths)
        self._secret_names = frozenset(name.lower() for name in secret_names)

    def apply(self, value: object) -> object:
        """Return a copy of the value with sensitive data masked."""
        return self._mask_by_name(self._mask_by_path(value))

    def _mask_by_path(self, value: object) -> object:
        if not self._glom_paths:
            return value

        # The branches match, but sanitize uses a TypeVar with two allowed types,
        # so it cannot accept the dict | list union.
        if isinstance(value, dict):
            return sanitize(cast("dict[str, object]", value), self._glom_paths)
        if isinstance(value, list):
            return sanitize(cast("list[object]", value), self._glom_paths)

        return value

    def _mask_by_name(self, value: object) -> object:
        if not self._secret_names:
            return value

        if isinstance(value, dict):
            return {
                key: MASKED_VALUE if str(key).lower() in self._secret_names else self._mask_by_name(item)
                for key, item in cast("dict[object, object]", value).items()
            }

        if isinstance(value, list):
            return [self._mask_by_name(item) for item in cast("list[object]", value)]

        return value
