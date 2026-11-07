from collections.abc import Sequence
from copy import deepcopy

import glom


def sanitize[T](
    value_to_sanitize: T,
    sensitive_keys: Sequence[str],
) -> T:
    """Создать новый словарь со скрытыми конфиденциальными данными.

    :param value_to_sanitize: словарь или список, который необходимо обработать.
    :param sensitive_keys: ключи в формате [glom](https://glom.readthedocs.io/en/latest/), которые необходимо скрыть.
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

    for sensitive_key in sensitive_keys:
        if glom.glom(value, sensitive_key, default=None) is None:
            continue

        glom.assign(value, sensitive_key, "****")

    return value
