from collections.abc import Sequence
from copy import deepcopy
from typing import cast

import glom


def sanitize[T](
    value_to_sanitize: T,
    sensitive_keys: Sequence[str],
) -> T:
    """Создать новый словарь со скрытыми конфиденциальными данными.

    :param value_to_sanitize: словарь или список, который необходимо обработать.
    :param sensitive_keys: имена скрываемых полей на любой глубине или точные пути glom.
    :returns: новый словарь или список со скрытыми конфиденциальными данными.

    #### Примеры:
    >>> result = sanitize({"d": {"password": "123123"}, "v": 123123}, ["d.password"])
    >>> assert result == {'d': {'password': '****'}, "v": 123123}

    >>> result = sanitize([{"d": {"passwd": "123123"}, "v": 123123}], ["*.d.passwd"])
    >>> assert result == [{'d': {'passwd': '****'}, "v": 123123}]

    >>> result = sanitize({"d": [{"passwd": "123123"}, {"passwd": "123123"}]}, ["d.*.passwd"])
    >>> assert result == {"d": [{"passwd": "****"}, {"passwd": "****"}]}
    """
    if len(sensitive_keys) == 0:
        return value_to_sanitize

    value = deepcopy(value_to_sanitize)
    names = frozenset(key for key in sensitive_keys if not any(character in key for character in ".*[()"))
    _mask_nested_fields(value, names)

    for sensitive_key in sensitive_keys:
        if glom.glom(value, sensitive_key, default=None) is None:
            continue

        glom.assign(value, sensitive_key, "****")

    return value


def _mask_nested_fields(value: object, names: frozenset[str]) -> None:
    pending = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, dict):
            mapping = cast("dict[object, object]", current)
            for key in mapping:
                if key in names:
                    mapping[key] = "****"
            pending.extend(mapping.values())
        elif isinstance(current, list):
            pending.extend(cast("list[object]", current))
