import os
from collections.abc import Callable
from uuid import uuid4

import grpc

from grpc_client.metadata import contains_key
from grpc_client.types import MetadataItems
from grpc_client.utils import traceparent

from .base import AsyncMetadataInterceptor, MetadataInterceptor, call_detail

DEFAULT_REQUEST_ID_KEY = "x-request-id"
DEFAULT_TRACEPARENT_KEY = "traceparent"


def default_request_id_key() -> str:
    """Получить имя ключа идентификатора запроса по умолчанию."""
    return os.getenv("GRPC_CLIENT_REQUEST_ID_KEY", DEFAULT_REQUEST_ID_KEY)


def default_traceparent_key() -> str:
    """Получить имя ключа traceparent по умолчанию."""
    return os.getenv("GRPC_CLIENT_TRACEPARENT_KEY", DEFAULT_TRACEPARENT_KEY)


class _AutogenerateMixin:
    """Общая логика интерцепторов, добавляющих сгенерированное значение в метаданные."""

    def __init__(self, key: str, generator: Callable[[], str]) -> None:
        """Создать экземпляр с переданными настройками."""
        self._key = key
        self._generator = generator

    def _metadata_to_add(self, call_details: grpc.ClientCallDetails | grpc.aio.ClientCallDetails) -> MetadataItems:
        if contains_key(call_detail(call_details, "metadata", None), self._key):
            return ()
        return ((self._key, self._generator()),)


class AutogenerateRequestIdInterceptor(_AutogenerateMixin, MetadataInterceptor):
    """Интерцептор, добавляющий идентификатор к каждому gRPC-запросу.

    Если запрос уже содержит такой ключ, значение сохраняется.
    """

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Инициализатор.

        :param key: имя ключа метаданных, по умолчанию `x-request-id`
        :param generator: функция генерации значения, по умолчанию UUID4
        """
        super().__init__(key or default_request_id_key(), generator or _uuid4)

    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Собрать идентификатор запроса, если его еще нет в метаданных."""
        return self._metadata_to_add(call_details)


class AsyncAutogenerateRequestIdInterceptor(_AutogenerateMixin, AsyncMetadataInterceptor):
    """Асинхронный интерцептор, добавляющий идентификатор к каждому gRPC-запросу."""

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Инициализатор.

        :param key: имя ключа метаданных, по умолчанию `x-request-id`
        :param generator: функция генерации значения, по умолчанию UUID4
        """
        super().__init__(key or default_request_id_key(), generator or _uuid4)

    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Собрать идентификатор запроса, если его еще нет в метаданных."""
        return self._metadata_to_add(call_details)


class AutogenerateTraceparentInterceptor(_AutogenerateMixin, MetadataInterceptor):
    """Интерцептор, добавляющий traceparent к каждому gRPC-запросу.

    Если запрос уже содержит traceparent, значение сохраняется.
    """

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Инициализатор.

        :param key: имя ключа метаданных, по умолчанию `traceparent`
        :param generator: функция генерации значения, по умолчанию генератор W3C Trace Context
        """
        super().__init__(key or default_traceparent_key(), generator or traceparent.generate)

    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Собрать traceparent, если его еще нет в метаданных."""
        return self._metadata_to_add(call_details)


class AsyncAutogenerateTraceparentInterceptor(_AutogenerateMixin, AsyncMetadataInterceptor):
    """Асинхронный интерцептор, добавляющий traceparent к каждому gRPC-запросу."""

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Инициализатор.

        :param key: имя ключа метаданных, по умолчанию `traceparent`
        :param generator: функция генерации значения, по умолчанию генератор W3C Trace Context
        """
        super().__init__(key or default_traceparent_key(), generator or traceparent.generate)

    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Собрать traceparent, если его еще нет в метаданных."""
        return self._metadata_to_add(call_details)


def _uuid4() -> str:
    return str(uuid4())
