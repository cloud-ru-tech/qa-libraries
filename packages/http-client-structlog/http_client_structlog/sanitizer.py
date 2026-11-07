from collections.abc import Iterable, Sequence
from typing import cast

from http_client.utils.sanitizer import sanitize

MASKED_VALUE = "****"


class Sanitizer:
    """Правила скрытия конфиденциальных данных в логе.

    Точные пути и типовые имена ищутся по-разному. Путь `user.password` указывает на одно
    конкретное поле, а `password` из списка типовых секретов должен срабатывать на любой
    глубине: секрет одинаково опасен и в корне тела, и внутри вложенного объекта.
    """

    def __init__(
        self,
        glom_paths: Sequence[str] = (),
        secret_names: Iterable[str] = (),
    ) -> None:
        """Создать экземпляр с указанными настройками."""
        self._glom_paths = tuple(glom_paths)
        self._secret_names = frozenset(name.lower() for name in secret_names)

    def apply(self, value: object) -> object:
        """Вернуть копию значения со скрытыми конфиденциальными данными."""
        return self._mask_by_name(self._mask_by_path(value))

    def _mask_by_path(self, value: object) -> object:
        if not self._glom_paths:
            return value

        # Ветки одинаковые, но sanitize объявлен через TypeVar с двумя допустимыми
        # типами, поэтому объединение dict | list ему передать нельзя.
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
