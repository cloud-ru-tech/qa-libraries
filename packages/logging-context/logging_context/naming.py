import hashlib
import re
from typing import Final, Protocol, cast

import pytest

# Всё, что не входит в этот набор, заменяется на "_". Разделители пути,
# NUL и спецсимволы Windows заведомо не проходят.
_FORBIDDEN: Final = re.compile(r"[^A-Za-z0-9._\[\]()-]+")

# Лимит имени файла в большинстве файловых систем — 255 байт, а не символов.
# Оставляем запас на суффикс попытки и расширение.
MAX_FILENAME_BYTES: Final = 200

_HASH_LENGTH: Final = 16


class _Callspec(Protocol):
    id: str
    params: dict[str, object]


def hash_params(params_id: str) -> str:
    """Вычислить стабильный короткий хеш идентификатора параметров теста."""
    return hashlib.sha256(params_id.encode()).hexdigest()[-_HASH_LENGTH:]


def slugify(value: str, max_bytes: int = MAX_FILENAME_BYTES) -> str:
    """Превратить произвольную строку в безопасный компонент имени файла.

    Гарантирует отсутствие разделителей пути и укладывается в `max_bytes` байт
    в кодировке UTF-8.
    """
    slug = _FORBIDDEN.sub("_", value).strip("._") or "unnamed"

    encoded = slug.encode()
    if len(encoded) <= max_bytes:
        return slug

    # Обрезаем по байтам, а не по символам, и не разрываем UTF-8 последовательность.
    # Суффикс из хеша сохраняет различимость обрезанных имён.
    suffix = f"-{hash_params(slug)}"
    keep = max_bytes - len(suffix.encode())
    truncated = encoded[:keep].decode(errors="ignore")
    return f"{truncated}{suffix}"


def _callspec_id(item: pytest.Item) -> str | None:
    """Идентификатор набора параметров теста.

    `callspec` — внутренний атрибут pytest.Function, официального публичного
    аналога нет, поэтому обращаемся через getattr.
    """
    callspec = cast("_Callspec | None", getattr(item, "callspec", None))
    return None if callspec is None else str(callspec.id)


def params_of(item: pytest.Item) -> dict[str, object] | None:
    """Параметры параметризованного теста."""
    callspec = cast("_Callspec | None", getattr(item, "callspec", None))
    return None if callspec is None else dict(callspec.params)


def build_test_name(item: pytest.Item) -> str:
    """Читаемое имя теста для имени файла: параметры заменены их хешом."""
    params_id = _callspec_id(item)
    if params_id is None:
        return slugify(item.name)

    original_name = cast("str | None", getattr(item, "originalname", None)) or item.name
    return slugify(f"{original_name}[{hash_params(params_id)}]")


def build_test_id(item: pytest.Item) -> str:
    """Идентификатор теста: nodeid, в котором параметры заменены их хешом.

    В отличие от замены по регулярному выражению, трогает только собственную
    параметризацию теста — квадратные скобки в пути каталога остаются как есть.
    """
    params_id = _callspec_id(item)
    if params_id is None:
        return item.nodeid

    suffix = f"[{params_id}]"
    if not item.nodeid.endswith(suffix):
        return item.nodeid

    return f"{item.nodeid[: -len(suffix)]}[{hash_params(params_id)}]"
