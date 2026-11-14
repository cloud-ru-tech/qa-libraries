import hashlib
import re
from typing import Final, Protocol, cast

import pytest

# Anything outside this set is replaced with "_". Path separators,
# NUL and Windows special characters are always rejected.
_FORBIDDEN: Final = re.compile(r"[^A-Za-z0-9._\[\]()-]+")

# Most filesystems limit filenames to 255 bytes, not characters.
# Leave room for the attempt suffix and extension.
MAX_FILENAME_BYTES: Final = 200

_HASH_LENGTH: Final = 16


class _Callspec(Protocol):
    id: str
    params: dict[str, object]


def hash_params(params_id: str) -> str:
    """Calculate a stable short hash of the test parameter identifier."""
    return hashlib.sha256(params_id.encode()).hexdigest()[-_HASH_LENGTH:]


def slugify(value: str, max_bytes: int = MAX_FILENAME_BYTES) -> str:
    """Convert an arbitrary string into a safe filename component.

    Guarantee no path separators and a size within `max_bytes` bytes
    in UTF-8 encoding.
    """
    slug = _FORBIDDEN.sub("_", value).strip("._") or "unnamed"

    encoded = slug.encode()
    if len(encoded) <= max_bytes:
        return slug

    # Truncate by bytes rather than characters without splitting UTF-8 sequences.
    # A hash suffix keeps truncated names distinguishable.
    suffix = f"-{hash_params(slug)}"
    keep = max_bytes - len(suffix.encode())
    truncated = encoded[:keep].decode(errors="ignore")
    return f"{truncated}{suffix}"


def _callspec_id(item: pytest.Item) -> str | None:
    """Get the identifier of the test parameter set.

    `callspec` is an internal pytest.Function attribute with no official public
    equivalent, so access it using getattr.
    """
    callspec = cast("_Callspec | None", getattr(item, "callspec", None))
    return None if callspec is None else str(callspec.id)


def params_of(item: pytest.Item) -> dict[str, object] | None:
    """Parameters of a parametrized test."""
    callspec = cast("_Callspec | None", getattr(item, "callspec", None))
    return None if callspec is None else dict(callspec.params)


def build_test_name(item: pytest.Item) -> str:
    """Readable test name for filenames, with parameters replaced by their hash."""
    params_id = _callspec_id(item)
    if params_id is None:
        return slugify(item.name)

    original_name = cast("str | None", getattr(item, "originalname", None)) or item.name
    return slugify(f"{original_name}[{hash_params(params_id)}]")


def build_test_id(item: pytest.Item) -> str:
    """Test identifier: nodeid with parameters replaced by their hash.

    Unlike regular expression replacement, this only modifies the actual
    test parametrization; square brackets in directory paths remain unchanged.
    """
    params_id = _callspec_id(item)
    if params_id is None:
        return item.nodeid

    suffix = f"[{params_id}]"
    if not item.nodeid.endswith(suffix):
        return item.nodeid

    return f"{item.nodeid[: -len(suffix)]}[{hash_params(params_id)}]"
