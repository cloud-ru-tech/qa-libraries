import re
from collections.abc import Sequence
from copy import deepcopy
from typing import cast

import glom

from grpc_client.metadata import as_metadata_items
from grpc_client.types import MetadataItems, MetadataType

# Replacement value for sensitive data.
MASK = "****"

# Replacement value for a subtree that masking did not reach.
DEPTH_EXCEEDED = "<превышена глубина вложенности>"

# Keys masked in logs by default.
DEFAULT_SANITIZE_KEYS: tuple[str, ...] = (
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "api_key",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "token",
)


_PATH_MARKERS = (".", "*", "[", "(")


def sanitize[T](value_to_sanitize: T, sensitive_keys: Sequence[str]) -> T:
    """Create a copy of the structure with sensitive data hidden.

    A key without separators is treated as a field name and masked at any nesting level:
    otherwise common names such as `password` would hide secrets only at the message root.
    A key with a dot, asterisk, or brackets is treated as a path for
    [glom](https://glom.readthedocs.io/en/latest/) and is applied unchanged.

    :param value_to_sanitize: dictionary or list to process
    :param sensitive_keys: field names or glom paths whose values should be hidden
    :return: new structure with sensitive data hidden

    #### Examples:
    >>> result = sanitize({"user": {"password": "123123"}, "v": 123123}, ["password"])
    >>> assert result == {"user": {"password": "****"}, "v": 123123}

    >>> result = sanitize({"d": {"password": "123123"}, "v": 123123}, ["d.password"])
    >>> assert result == {"d": {"password": "****"}, "v": 123123}

    >>> result = sanitize([{"d": {"passwd": "123123"}, "v": 123123}], ["*.d.passwd"])
    >>> assert result == [{"d": {"passwd": "****"}, "v": 123123}]

    >>> result = sanitize({"d": [{"passwd": "123123"}, {"passwd": "123123"}]}, ["d.*.passwd"])
    >>> assert result == {"d": [{"passwd": "****"}, {"passwd": "****"}]}
    """
    if len(sensitive_keys) == 0:
        return deepcopy(value_to_sanitize)

    names = {_normalized_name(key) for key in sensitive_keys if not _is_glom_path(key)}
    paths = [key for key in sensitive_keys if _is_glom_path(key)]

    # Name-based masking builds a new structure, so a copy is needed only
    # for glom: it changes values in place, and the original message must remain unchanged.
    value = _mask_by_name(value_to_sanitize, names) if names else deepcopy(value_to_sanitize)
    if names and paths:
        value = deepcopy(value)

    for path in paths:
        if glom.glom(value, path, default=None) is None:
            continue

        glom.assign(value, path, MASK)

    return cast("T", value)


def _is_glom_path(key: str) -> bool:
    """Determine whether a key is a glom path rather than a field name."""
    return any(marker in key for marker in _PATH_MARKERS)


def _normalized_name(name: str) -> str:
    """Normalize a field name to snake_case regardless of naming style.

    protobuf serializes `access_token` as `accessToken`, so comparing names
    character by character would leave secrets visible solely due to a different naming style.
    Preserve word boundaries, otherwise the harmless `sec_ret` field would match `secret`.

    Support acronyms (`APIKey`), digits (`token2FA`), leading separators
    (`_accessToken`), as well as non-Latin scripts.

    :param name: field name
    :return: snake_case name
    """
    stripped = name.strip("_-")

    parts: list[str] = []
    for index, char in enumerate(stripped):
        if _needs_boundary(stripped, index):
            parts.append("_")
        parts.append(char)

    return re.sub(r"[-_]+", "_", "".join(parts)).lower()


# Maximum traversal depth for field name masking.
MAX_DEPTH = 64


def _needs_boundary(name: str, index: int) -> bool:
    """Determine whether a word boundary is needed before a character.

    Rules use Unicode properties rather than the Latin alphabet: field names
    occur in other scripts too.

    :param name: field name without leading separators
    :param index: position of the character to check
    :return: True if a separator is needed before the character
    """
    if index == 0:
        return False

    current = name[index]
    previous = name[index - 1]

    if previous in "_-" or current in "_-":
        return False

    # accessToken -> access_Token, password2 -> password_2, 用户Token -> 用户_Token.
    # Scripts without case also count as a left boundary, otherwise a secret in a mixed-script
    # name would remain unrecognized.
    previous_starts_word = previous.islower() or previous.isdigit() or (previous.isalpha() and not previous.isupper())
    if (current.isupper() or current.isdigit()) and previous_starts_word:
        return current.isupper() or not previous.isdigit()

    # APIKey -> API_Key
    if current.isupper() and previous.isupper():
        following = name[index + 1] if index + 1 < len(name) else ""
        return following.islower()

    # token2FA -> token_2_FA
    return previous.isdigit() and not current.isdigit()


def _is_sensitive(normalized: str, names: set[str]) -> bool:
    """Check whether a field name denotes a secret.

    A match is either the name itself or a compound name ending in it:
    `user_password` and `client_secret` are secrets just like `password` and `secret`.
    Substring matching would incorrectly mask the harmless `tokenizer`.

    :param normalized: normalized field name
    :param names: normalized secret names
    :return: True if the field value must be hidden
    """
    if normalized in names:
        return True
    return any(normalized.endswith(f"_{name}") for name in names)


def _mask_by_name(value: object, names: set[str], depth: int = 0) -> object:
    """Mask values of fields with the specified names at any nesting level.

    Traversal depth is limited: a recursively structured message would otherwise break
    log preparation and therefore the request itself.

    :param value: structure to process
    :param names: normalized field names
    :param depth: current traversal depth
    :return: structure with masked values
    """
    if depth >= MAX_DEPTH:
        # Stop descending, but do not return the content unchanged: it may contain a secret
        # that masking simply did not reach.
        return DEPTH_EXCEEDED if isinstance(value, dict | list) else value

    if isinstance(value, dict):
        return {
            key: MASK
            if isinstance(key, str) and _is_sensitive(_normalized_name(key), names)
            else _mask_by_name(item, names, depth + 1)
            for key, item in cast("dict[object, object]", value).items()
        }
    if isinstance(value, list):
        return [_mask_by_name(item, names, depth + 1) for item in value]
    return value


def sanitize_metadata(metadata: MetadataType | None, sensitive_keys: Sequence[str]) -> MetadataItems:
    """Hide sensitive metadata values.

    gRPC metadata is flat and its keys may contain dots, so compare
    complete key names without parsing glom paths. Matching is case-insensitive.

    :param metadata: metadata to process
    :param sensitive_keys: key names whose values should be hidden
    :return: metadata with sensitive key values hidden
    """
    masked = {key.lower() for key in sensitive_keys}
    return tuple((name, MASK if name.lower() in masked else value) for name, value in as_metadata_items(metadata))
