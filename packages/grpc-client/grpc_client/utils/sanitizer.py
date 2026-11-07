import re
from collections.abc import Sequence
from copy import deepcopy
from typing import cast

import glom

from grpc_client.metadata import as_metadata_items
from grpc_client.types import MetadataItems, MetadataType

# Значение, которым заменяются конфиденциальные данные.
MASK = "****"

# Значение, которым заменяется поддерево, до которого маскирование не дошло.
DEPTH_EXCEEDED = "<превышена глубина вложенности>"

# Ключи, которые маскируются в логах по умолчанию.
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
    """Создать копию структуры со скрытыми конфиденциальными данными.

    Ключ без разделителей считается именем поля и маскируется на любом уровне вложенности:
    иначе типовые имена вроде `password` скрывали бы секрет только в корне сообщения.
    Ключ с точкой, звездочкой или скобками считается путем
    [glom](https://glom.readthedocs.io/en/latest/) и применяется как есть.

    :param value_to_sanitize: словарь или список, который необходимо обработать
    :param sensitive_keys: имена полей либо пути glom, значения которых нужно скрыть
    :return: новая структура со скрытыми конфиденциальными данными

    #### Примеры:
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

    # Маскирование по имени само собирает новую структуру, поэтому копия нужна только
    # ради glom: он изменяет значения на месте, а исходное сообщение трогать нельзя.
    value = _mask_by_name(value_to_sanitize, names) if names else deepcopy(value_to_sanitize)
    if names and paths:
        value = deepcopy(value)

    for path in paths:
        if glom.glom(value, path, default=None) is None:
            continue

        glom.assign(value, path, MASK)

    return cast("T", value)


def _is_glom_path(key: str) -> bool:
    """Определить, задан ли ключ путем glom, а не именем поля."""
    return any(marker in key for marker in _PATH_MARKERS)


def _normalized_name(name: str) -> str:
    """Привести имя поля к snake_case, не зависящему от стиля записи.

    protobuf сериализует `access_token` как `accessToken`, поэтому сравнивать имена
    посимвольно нельзя: секрет остался бы в логе только из-за другого стиля записи.
    Границы слов при этом сохраняются, иначе безобидное поле `sec_ret` совпало бы с `secret`.

    Учитываются аббревиатуры (`APIKey`), цифры (`token2FA`), ведущие разделители
    (`_accessToken`) и не только латиница.

    :param name: имя поля
    :return: имя в snake_case
    """
    stripped = name.strip("_-")

    parts: list[str] = []
    for index, char in enumerate(stripped):
        if _needs_boundary(stripped, index):
            parts.append("_")
        parts.append(char)

    return re.sub(r"[-_]+", "_", "".join(parts)).lower()


# Предельная глубина обхода структуры при маскировании по имени поля.
MAX_DEPTH = 64


def _needs_boundary(name: str, index: int) -> bool:
    """Определить, нужна ли граница слова перед символом.

    Правила работают по свойствам Unicode, а не по латинскому алфавиту: имена полей
    встречаются и на других письменностях.

    :param name: имя поля без ведущих разделителей
    :param index: позиция проверяемого символа
    :return: True, если перед символом нужен разделитель
    """
    if index == 0:
        return False

    current = name[index]
    previous = name[index - 1]

    if previous in "_-" or current in "_-":
        return False

    # accessToken -> access_Token, пароль2 -> пароль_2, 用户Token -> 用户_Token.
    # Письменности без регистра тоже считаются левой границей: иначе секрет в смешанном
    # имени остался бы неузнанным.
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
    """Проверить, что имя поля обозначает секрет.

    Совпадением считается как само имя, так и составное имя, оканчивающееся на него:
    `user_password` и `client_secret` — такие же секреты, как `password` и `secret`.
    Поиск подстроки здесь не годится: он замаскировал бы безобидный `tokenizer`.

    :param normalized: имя поля в нормализованном виде
    :param names: нормализованные имена секретов
    :return: True, если значение поля нужно скрыть
    """
    if normalized in names:
        return True
    return any(normalized.endswith(f"_{name}") for name in names)


def _mask_by_name(value: object, names: set[str], depth: int = 0) -> object:
    """Замаскировать значения полей с указанными именами на любом уровне вложенности.

    Обход ограничен по глубине: сообщение с рекурсивной структурой иначе уронило бы
    подготовку лога, а вместе с ней и сам запрос.

    :param value: обрабатываемая структура
    :param names: нормализованные имена полей
    :param depth: текущая глубина обхода
    :return: структура с замаскированными значениями
    """
    if depth >= MAX_DEPTH:
        # Дальше не идем, но и отдавать содержимое как есть нельзя: в нем может быть секрет,
        # до которого маскирование просто не добралось.
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
    """Скрыть конфиденциальные данные в метаданных.

    Метаданные gRPC плоские, а их ключи могут содержать точку, поэтому здесь сравниваются
    имена ключей целиком, без разбора glom-путей. Регистр не учитывается.

    :param metadata: метаданные, которые необходимо обработать
    :param sensitive_keys: имена ключей, значения которых нужно скрыть
    :return: метаданные со скрытыми значениями конфиденциальных ключей
    """
    masked = {key.lower() for key in sensitive_keys}
    return tuple((name, MASK if name.lower() in masked else value) for name, value in as_metadata_items(metadata))
