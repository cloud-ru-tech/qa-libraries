from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from api import grpcbin_pb2, grpcbin_pb2_grpc
from grpc_client import (
    AsyncGRPCClient,
    AsyncGRPCStreamResponse,
    CallOptions,
    GRPCClient,
    GRPCResponse,
    GRPCStreamResponse,
    MetadataType,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    import grpc


class GrpcbinStub(Protocol):
    HeadersUnary: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.HeadersMessage]
    SpecificError: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.SpecificErrorRequest, grpcbin_pb2.EmptyMessage]
    DummyUnary: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]
    Empty: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.EmptyMessage]
    NoResponseUnary: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.EmptyMessage]
    DummyClientStream: grpc.StreamUnaryMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]
    DummyServerStream: grpc.UnaryStreamMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]
    DummyBidirectionalStreamStream: grpc.StreamStreamMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]

    def __init__(self, channel: grpc.Channel) -> None:
        """Создать stub тестового сервиса."""


class AsyncGrpcbinStub(Protocol):
    HeadersUnary: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.HeadersMessage]
    SpecificError: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.SpecificErrorRequest, grpcbin_pb2.EmptyMessage]
    DummyUnary: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]
    Empty: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.EmptyMessage]
    NoResponseUnary: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.EmptyMessage]
    DummyClientStream: grpc.aio.StreamUnaryMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]
    DummyServerStream: grpc.aio.UnaryStreamMultiCallable[grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage]
    DummyBidirectionalStreamStream: grpc.aio.StreamStreamMultiCallable[
        grpcbin_pb2.DummyMessage, grpcbin_pb2.DummyMessage
    ]

    def __init__(self, channel: grpc.aio.Channel) -> None:
        """Создать stub тестового сервиса."""


class GRPCbinServiceClient(GRPCClient[GrpcbinStub]):
    """gRPC-клиент сервиса «GRPCBin»."""

    @property
    def stub_class(self) -> type[GrpcbinStub]:
        return cast("type[GrpcbinStub]", grpcbin_pb2_grpc.GRPCBinStub)

    def dummy_unary(
        self,
        msg: grpcbin_pb2.DummyMessage,
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Отправить сообщение и получить его же в ответ.

        :param msg: сообщение серверу
        :param metadata: метаданные запроса
        :param options: параметры вызова
        :return: ответ с тем же сообщением
        """
        return self.send_unary_unary_request(msg, self.stub.DummyUnary, metadata, options)

    def empty(self, options: CallOptions | None = None) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Вызвать метод, возвращающий пустое сообщение.

        :param options: параметры вызова
        :return: ответ с пустым сообщением
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.Empty, options=options)

    def specific_error(self, code: int, reason: str) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Попросить сервис ответить заданной ошибкой.

        :param code: код ошибки gRPC
        :param reason: текст ошибки
        :return: ответ с запрошенной ошибкой
        """
        return self.send_unary_unary_request(
            grpcbin_pb2.SpecificErrorRequest(code=code, reason=reason),
            self.stub.SpecificError,
        )

    def no_response(self, options: CallOptions | None = None) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Вызвать метод, который не отвечает.

        :param options: параметры вызова
        :return: ответ, которого сервис не пришлет
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.NoResponseUnary, options=options)

    def send_client_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Отправить поток сообщений и получить одно в ответ.

        :param messages: поток сообщений
        :return: ответ с сообщением от сервера
        """
        return self.send_stream_unary_request(messages, self.stub.DummyClientStream)

    def send_server_stream(
        self,
        msg: grpcbin_pb2.DummyMessage,
        options: CallOptions | None = None,
    ) -> GRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Отправить сообщение и получить поток сообщений.

        :param msg: сообщение серверу
        :param options: параметры вызова
        :return: поток ответных сообщений
        """
        return self.send_unary_stream_request(msg, self.stub.DummyServerStream, options=options)

    def send_bidirectional_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
        options: CallOptions | None = None,
    ) -> GRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Отправить поток сообщений и получить поток в ответ.

        :param messages: поток сообщений
        :param options: параметры вызова
        :return: поток ответных сообщений
        """
        return self.send_stream_stream_request(
            messages,
            self.stub.DummyBidirectionalStreamStream,
            options=options,
        )

    def get_headers(
        self,
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[grpcbin_pb2.HeadersMessage]:
        """Получить метаданные, которые сервис увидел в запросе.

        :param metadata: метаданные запроса
        :param options: параметры вызова
        :return: ответ с метаданными запроса
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.HeadersUnary, metadata, options)


class AsyncGRPCbinServiceClient(AsyncGRPCClient[AsyncGrpcbinStub]):
    """Асинхронный gRPC-клиент сервиса «GRPCBin»."""

    @property
    def stub_class(self) -> type[AsyncGrpcbinStub]:
        return cast("type[AsyncGrpcbinStub]", grpcbin_pb2_grpc.GRPCBinStub)

    async def dummy_unary(
        self,
        msg: grpcbin_pb2.DummyMessage,
        metadata: MetadataType | None = None,
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Отправить сообщение и получить его же в ответ.

        :param msg: сообщение серверу
        :param metadata: метаданные запроса
        :return: ответ с тем же сообщением
        """
        return await self.send_unary_unary_request(msg, self.stub.DummyUnary, metadata)

    async def specific_error(self, code: int, reason: str) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Попросить сервис ответить заданной ошибкой.

        :param code: код ошибки gRPC
        :param reason: текст ошибки
        :return: ответ с запрошенной ошибкой
        """
        return await self.send_unary_unary_request(
            grpcbin_pb2.SpecificErrorRequest(code=code, reason=reason),
            self.stub.SpecificError,
        )

    async def send_server_stream(
        self,
        msg: grpcbin_pb2.DummyMessage,
        options: CallOptions | None = None,
    ) -> AsyncGRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Отправить сообщение и получить поток сообщений.

        :param msg: сообщение серверу
        :param options: параметры вызова
        :return: поток ответных сообщений
        """
        return await self.send_unary_stream_request(msg, self.stub.DummyServerStream, options=options)

    async def send_client_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Отправить поток сообщений и получить одно в ответ.

        :param messages: поток сообщений
        :return: ответ с сообщением от сервера
        """
        return await self.send_stream_unary_request(messages, self.stub.DummyClientStream)

    async def send_bidirectional_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
    ) -> AsyncGRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Отправить поток сообщений и получить поток в ответ.

        :param messages: поток сообщений
        :return: поток ответных сообщений
        """
        return await self.send_stream_stream_request(messages, self.stub.DummyBidirectionalStreamStream)

    async def get_headers(self, metadata: MetadataType | None = None) -> GRPCResponse[grpcbin_pb2.HeadersMessage]:
        """Получить метаданные, которые сервис увидел в запросе.

        :param metadata: метаданные запроса
        :return: ответ с метаданными запроса
        """
        return await self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.HeadersUnary, metadata)
