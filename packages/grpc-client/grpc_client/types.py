from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

import grpc

# Значение метаданных gRPC.
#
# Двоичные значения допустимы только для ключей с суффиксом `-bin`, остальные должны быть строками.
MetadataValue = str | bytes

# Метаданные в виде последовательности пар, допускающей повторяющиеся ключи.
MetadataItems = Sequence[tuple[str, MetadataValue]]

# Метаданные запроса: словарь либо последовательность пар.
MetadataType = Mapping[str, MetadataValue] | MetadataItems

# Низкоуровневые настройки канала grpcio.
ChannelOptions = Sequence[tuple[str, object]]


@runtime_checkable
class GRPCStub(Protocol):
    """Сгенерированный Stub сервиса, работающий поверх синхронного канала."""

    def __init__(self, channel: grpc.Channel) -> None:
        """Создать stub поверх синхронного канала."""


@runtime_checkable
class AsyncGRPCStub(Protocol):
    """Сгенерированный Stub сервиса, работающий поверх асинхронного канала."""

    def __init__(self, channel: grpc.aio.Channel) -> None:
        """Создать stub поверх асинхронного канала."""


class ClientAuth(Protocol):
    """Источник токена доступа для синхронного клиента.

    Протокол объявлен без `runtime_checkable`: `isinstance()` проверяет лишь наличие методов
    и не отличает синхронную реализацию от асинхронной, поэтому такая проверка вводила бы
    в заблуждение. Клиент различает их по тому, объявлен ли `token()` корутиной.

    Реализация отвечает только за выдачу токена: кеширование, срок жизни и поход во внешний сервис —
    ее забота. Подстановку токена в метаданные и повтор запроса после `UNAUTHENTICATED` берет на себя клиент.
    """

    def token(self) -> str:
        """Получить действующий токен доступа."""
        ...

    def refresh(self, rejected_token: str) -> str:
        """Выпустить новый токен взамен отвергнутого сервисом.

        Отвергнутый токен передается, чтобы реализация могла отличить «токен действительно протух»
        от «пока мы ждали, его уже обновил кто-то другой» и не ходила во внешний сервис лишний раз.

        :param rejected_token: токен, который сервис отверг с ошибкой UNAUTHENTICATED
        :return: действующий токен доступа
        """
        ...


class AsyncClientAuth(Protocol):
    """Источник токена доступа для асинхронного клиента."""

    async def token(self) -> str:
        """Получить действующий токен доступа."""
        ...

    async def refresh(self, rejected_token: str) -> str:
        """Выпустить новый токен взамен отвергнутого сервисом.

        :param rejected_token: токен, который сервис отверг с ошибкой UNAUTHENTICATED
        :return: действующий токен доступа
        """
        ...
