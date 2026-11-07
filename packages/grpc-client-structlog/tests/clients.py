from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from google.protobuf.struct_pb2 import Struct
from grpc_client import (
    AsyncGRPCClient,
    AsyncGRPCStreamResponse,
    GRPCClient,
    GRPCResponse,
    GRPCStreamResponse,
    MetadataType,
)

from .service import BIDIRECTIONAL_METHOD, CLIENT_STREAM_METHOD, SERVER_STREAM_METHOD, UNARY_METHOD

if TYPE_CHECKING:
    from collections.abc import Iterator

    import grpc


class SyncEchoStub(Protocol):
    unary: grpc.UnaryUnaryMultiCallable[Struct, Struct]
    server_stream: grpc.UnaryStreamMultiCallable[Struct, Struct]
    client_stream: grpc.StreamUnaryMultiCallable[Struct, Struct]
    bidirectional_stream: grpc.StreamStreamMultiCallable[Struct, Struct]

    def __init__(self, channel: grpc.Channel) -> None:
        """Создать stub тестового сервиса."""


class AsyncEchoStub(Protocol):
    unary: grpc.aio.UnaryUnaryMultiCallable[Struct, Struct]
    server_stream: grpc.aio.UnaryStreamMultiCallable[Struct, Struct]
    client_stream: grpc.aio.StreamUnaryMultiCallable[Struct, Struct]
    bidirectional_stream: grpc.aio.StreamStreamMultiCallable[Struct, Struct]

    def __init__(self, channel: grpc.aio.Channel) -> None:
        """Создать stub тестового сервиса."""


class EchoStub:
    """Stub тестового сервиса, собранный вручную вместо генерации из proto-файла.

    Один и тот же класс работает поверх синхронного и асинхронного канала: типы вызовов
    у них разные, поэтому методы не аннотированы конкретным типом multicallable.
    """

    def __init__(self, channel: grpc.Channel | grpc.aio.Channel) -> None:
        """Создать экземпляр с переданными настройками."""
        self.unary: object = channel.unary_unary(
            UNARY_METHOD,
            request_serializer=Struct.SerializeToString,
            response_deserializer=Struct.FromString,
        )
        self.server_stream: object = channel.unary_stream(
            SERVER_STREAM_METHOD,
            request_serializer=Struct.SerializeToString,
            response_deserializer=Struct.FromString,
        )
        self.client_stream: object = channel.stream_unary(
            CLIENT_STREAM_METHOD,
            request_serializer=Struct.SerializeToString,
            response_deserializer=Struct.FromString,
        )
        self.bidirectional_stream: object = channel.stream_stream(
            BIDIRECTIONAL_METHOD,
            request_serializer=Struct.SerializeToString,
            response_deserializer=Struct.FromString,
        )


class EchoClient(GRPCClient[SyncEchoStub]):
    """Синхронный клиент тестового сервиса."""

    @property
    def stub_class(self) -> type[SyncEchoStub]:
        return cast("type[SyncEchoStub]", EchoStub)

    def echo(self, msg: Struct, metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Отправить сообщение и получить его же в ответ.

        :param msg: сообщение серверу
        :param metadata: метаданные запроса
        :returns: ответ с тем же сообщением
        """
        return self.send_unary_unary_request(msg, self.stub.unary, metadata)

    def download(self, msg: Struct, metadata: MetadataType | None = None) -> GRPCStreamResponse[Struct]:
        """Отправить сообщение и получить поток сообщений.

        :param msg: сообщение серверу
        :param metadata: метаданные запроса
        :returns: поток ответных сообщений
        """
        return self.send_unary_stream_request(msg, self.stub.server_stream, metadata)

    def upload(self, messages: Iterator[Struct], metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Отправить поток сообщений и получить одно в ответ.

        :param messages: поток сообщений
        :param metadata: метаданные запроса
        :returns: ответ с количеством принятых сообщений
        """
        return self.send_stream_unary_request(messages, self.stub.client_stream, metadata)

    def chat(self, messages: Iterator[Struct], metadata: MetadataType | None = None) -> GRPCStreamResponse[Struct]:
        """Отправить поток сообщений и получить поток в ответ.

        :param messages: поток сообщений
        :param metadata: метаданные запроса
        :returns: поток ответных сообщений
        """
        return self.send_stream_stream_request(messages, self.stub.bidirectional_stream, metadata)


class AsyncEchoClient(AsyncGRPCClient[AsyncEchoStub]):
    """Асинхронный клиент тестового сервиса."""

    @property
    def stub_class(self) -> type[AsyncEchoStub]:
        return cast("type[AsyncEchoStub]", EchoStub)

    async def echo(self, msg: Struct, metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Отправить сообщение и получить его же в ответ.

        :param msg: сообщение серверу
        :param metadata: метаданные запроса
        :returns: ответ с тем же сообщением
        """
        return await self.send_unary_unary_request(msg, self.stub.unary, metadata)

    async def download(self, msg: Struct, metadata: MetadataType | None = None) -> AsyncGRPCStreamResponse[Struct]:
        """Отправить сообщение и получить поток сообщений.

        :param msg: сообщение серверу
        :param metadata: метаданные запроса
        :returns: поток ответных сообщений
        """
        return await self.send_unary_stream_request(msg, self.stub.server_stream, metadata)

    async def upload(self, messages: Iterator[Struct], metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Отправить поток сообщений и получить одно в ответ.

        :param messages: поток сообщений
        :param metadata: метаданные запроса
        :returns: ответ с количеством принятых сообщений
        """
        return await self.send_stream_unary_request(messages, self.stub.client_stream, metadata)

    async def chat(
        self,
        messages: Iterator[Struct],
        metadata: MetadataType | None = None,
    ) -> AsyncGRPCStreamResponse[Struct]:
        """Отправить поток сообщений и получить поток в ответ.

        :param messages: поток сообщений
        :param metadata: метаданные запроса
        :returns: поток ответных сообщений
        """
        return await self.send_stream_stream_request(messages, self.stub.bidirectional_stream, metadata)
