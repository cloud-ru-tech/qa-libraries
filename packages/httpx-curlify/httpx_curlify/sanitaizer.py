from collections.abc import Sequence
from copy import deepcopy

import glom


def sanitize[T](
    value_to_sanitize: T,
    sensitive_keys: Sequence[str],
) -> T:
    """Create a new dictionary with sensitive data masked.

    :param value_to_sanitize: Dictionary or list to process.
    :param sensitive_keys: Keys in [glom](https://glom.readthedocs.io/en/latest/) format, to mask.
    :returns: New dictionary or list with sensitive data masked.

    #### Examples:
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

    for sensitive_key in sensitive_keys:
        if glom.glom(value, sensitive_key, default=None) is None:
            continue

        glom.assign(value, sensitive_key, "****")

    return value
