from __future__ import annotations

from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypedDict, TypeVar

import grpc
from google.protobuf.message import Message

from .call_options import CallOptions
from .metadata import merge_metadata
from .types import AsyncGRPCStub, ChannelOptions, GRPCStub, MetadataItems, MetadataType

# Функция, настраивающая клиент при создании.
ClientOption = Callable[["BaseGRPCClient[object]"], None]

type ClientInterceptorTypes = (
    grpc.UnaryUnaryClientInterceptor[object, object]
    | grpc.UnaryStreamClientInterceptor[object, object]
    | grpc.StreamUnaryClientInterceptor[object, object]
    | grpc.StreamStreamClientInterceptor[object, object]
)
type AsyncClientInterceptorTypes = (
    grpc.aio.UnaryUnaryClientInterceptor[object, object]
    | grpc.aio.UnaryStreamClientInterceptor[object, object]
    | grpc.aio.StreamUnaryClientInterceptor[object, object]
    | grpc.aio.StreamStreamClientInterceptor[object, object]
)

TStub = TypeVar("TStub", bound=GRPCStub)
TAsyncStub = TypeVar("TAsyncStub", bound=AsyncGRPCStub)
TRequest = TypeVar("TRequest", bound=Message)
TResponse = TypeVar("TResponse", bound=Message)

DEFAULT_TIMEOUT_SEC = 60.0


class CallArguments(TypedDict):
    """Аргументы, передаваемые в методы grpcio."""

    timeout: float | None
    metadata: tuple[tuple[str, str | bytes], ...] | None
    credentials: grpc.CallCredentials | None
    wait_for_ready: bool | None
    compression: grpc.Compression | None


@dataclass(slots=True, kw_only=True)
class _ClientConfiguration:
    timeout: float | None = DEFAULT_TIMEOUT_SEC
    secure: bool = True
    ssl_credentials: grpc.ChannelCredentials | None = None
    compression: grpc.Compression | None = None
    channel_options: ChannelOptions = ()
    default_metadata: MetadataItems = ()


class BaseGRPCClient[TAnyStub](metaclass=ABCMeta):
    """Базовый абстрактный класс gRPC-клиента.

    Хранит настройки, общие для синхронного и асинхронного клиентов, применяет к ним опции
    и собирает из них итоговые параметры каждого вызова. Отправку запросов и работу с каналом
    реализуют наследники.
    """

    DEFAULT_TIMEOUT_SEC = DEFAULT_TIMEOUT_SEC

    def __init__(self) -> None:
        """Создать экземпляр с переданными настройками."""
        self._configuration = _ClientConfiguration(timeout=self.DEFAULT_TIMEOUT_SEC)
        self._interceptors: list[object] = []

    @property
    def timeout(self) -> float | None:
        """Ограничение времени вызова по умолчанию."""
        return self._configuration.timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self._configuration.timeout = value

    @property
    def secure(self) -> bool:
        """Признак использования TLS для нового канала."""
        return self._configuration.secure

    @secure.setter
    def secure(self, value: bool) -> None:
        self._configuration.secure = value

    @property
    def ssl_credentials(self) -> grpc.ChannelCredentials | None:
        """Учетные данные TLS для нового канала."""
        return self._configuration.ssl_credentials

    @ssl_credentials.setter
    def ssl_credentials(self, value: grpc.ChannelCredentials | None) -> None:
        self._configuration.ssl_credentials = value

    @property
    def compression(self) -> grpc.Compression | None:
        """Алгоритм сжатия сообщений."""
        return self._configuration.compression

    @compression.setter
    def compression(self, value: grpc.Compression | None) -> None:
        self._configuration.compression = value

    @property
    def channel_options(self) -> ChannelOptions:
        """Низкоуровневые параметры нового канала."""
        return self._configuration.channel_options

    @channel_options.setter
    def channel_options(self, value: ChannelOptions) -> None:
        self._configuration.channel_options = value

    @property
    def default_metadata(self) -> MetadataItems:
        """Метаданные, добавляемые к каждому запросу."""
        return self._configuration.default_metadata

    @default_metadata.setter
    def default_metadata(self, value: MetadataItems) -> None:
        self._configuration.default_metadata = value

    def add_interceptor(self, interceptor: object) -> None:
        """Добавить интерцептор до создания канала.

        :param interceptor: синхронный или асинхронный интерцептор grpcio.
        """
        self._interceptors.append(interceptor)

    @property
    @abstractmethod
    def stub_class(self) -> type[TAnyStub]:
        """Класс Stub-а сервиса из сгенерированного `***_pb2_grpc.py` файла."""

    def _apply(self, options: Sequence[ClientOption]) -> None:
        for option in options:
            option(self)

    def _credentials(self) -> grpc.ChannelCredentials:
        return self.ssl_credentials if self.ssl_credentials is not None else grpc.ssl_channel_credentials()

    def _call_options(self, metadata: MetadataType | None, options: CallOptions | None) -> CallOptions:
        """Собрать итоговые параметры вызова из настроек клиента и параметров запроса."""
        base = CallOptions(
            timeout=self.timeout,
            metadata=self.default_metadata,
            compression=self.compression,
        )
        request_options = options or CallOptions()
        if metadata is not None:
            request_options = CallOptions(
                timeout=request_options.timeout,
                metadata=merge_metadata(request_options.metadata, metadata),
                credentials=request_options.credentials,
                wait_for_ready=request_options.wait_for_ready,
                compression=request_options.compression,
            )
        return base.merge(request_options)

    @staticmethod
    def _call_kwargs(options: CallOptions) -> CallArguments:
        """Превратить параметры вызова в аргументы grpcio."""
        metadata = merge_metadata(options.metadata)
        return {
            "timeout": options.resolve_timeout(None),
            "metadata": tuple(metadata) or None,
            "credentials": options.credentials,
            "wait_for_ready": options.wait_for_ready,
            "compression": options.compression,
        }
