from collections.abc import Iterable, Iterator, Mapping
from typing import cast

from .types import MetadataItems, MetadataType, MetadataValue


def as_metadata_items(metadata: MetadataType | None) -> MetadataItems:
    """Привести метаданные к последовательности пар.

    :param metadata: метаданные в любом поддерживаемом виде
    :return: последовательность пар ключ-значение
    """
    if metadata is None:
        return ()
    if isinstance(metadata, Metadata):
        return metadata.pairs()
    if isinstance(metadata, Mapping):
        return tuple(metadata.items())
    return tuple(metadata)


def aio_metadata_items(metadata: object) -> MetadataItems:
    """Привести метаданные асинхронного вызова к последовательности пар.

    `grpc.aio` отдает собственный тип метаданных: он итерируется парами, но не является Sequence.

    :param metadata: метаданные асинхронного вызова
    :return: последовательность пар ключ-значение
    """
    if metadata is None:
        return ()
    return tuple(cast("Iterable[tuple[str, MetadataValue]]", metadata))


def merge_metadata(*sources: MetadataType | None) -> MetadataItems:
    """Объединить метаданные из нескольких источников с сохранением порядка.

    :param sources: наборы метаданных, каждый следующий дописывается в конец
    :return: последовательность пар ключ-значение
    """
    merged: list[tuple[str, MetadataValue]] = []
    for source in sources:
        merged.extend(as_metadata_items(source))
    return tuple(merged)


def contains_key(metadata: MetadataType | None, key: str) -> bool:
    """Проверить наличие ключа в метаданных без учета регистра.

    :param metadata: метаданные запроса
    :param key: искомый ключ
    :return: True, если ключ присутствует
    """
    normalized = key.lower()
    return any(name.lower() == normalized for name, _ in as_metadata_items(metadata))


class Metadata(Mapping[str, MetadataValue]):
    """Метаданные gRPC, сохраняющие порядок и повторяющиеся ключи.

    Ведет себя как словарь: по ключу отдает первое значение. Все значения ключа доступны через `get_all()`.
    Ключи сравниваются без учета регистра, как того требует HTTP/2.
    """

    __slots__ = ("_items",)

    def __init__(self, metadata: MetadataType | None = None) -> None:
        """Создать экземпляр с переданными настройками."""
        self._items: tuple[tuple[str, MetadataValue], ...] = tuple(as_metadata_items(metadata))

    def __getitem__(self, key: str) -> MetadataValue:
        """Вернуть первое значение ключа метаданных."""
        normalized = key.lower()
        for name, value in self._items:
            if name.lower() == normalized:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Получить итератор значений."""
        seen: set[str] = set()
        for name, _ in self._items:
            normalized = name.lower()
            if normalized not in seen:
                seen.add(normalized)
                yield name

    def __len__(self) -> int:
        """Получить число уникальных ключей метаданных."""
        return sum(1 for _ in iter(self))

    def __repr__(self) -> str:
        """Вернуть строковое представление метаданных."""
        return f"{type(self).__name__}({list(self._items)!r})"

    def get_all(self, key: str) -> tuple[MetadataValue, ...]:
        """Получить все значения ключа.

        :param key: имя ключа метаданных
        :return: значения в порядке получения, пустой кортеж — если ключа нет
        """
        normalized = key.lower()
        return tuple(value for name, value in self._items if name.lower() == normalized)

    def pairs(self) -> tuple[tuple[str, MetadataValue], ...]:
        """Получить все пары ключ-значение, включая повторяющиеся ключи.

        В отличие от `items()`, здесь сохраняются все значения повторяющихся ключей.
        """
        return self._items
