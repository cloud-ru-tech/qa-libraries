from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from api import grpcbin_pb2, grpcbin_pb2_grpc
from grpc_client import AsyncGRPCClient, GRPCClient, GRPCResponse, MetadataType

if TYPE_CHECKING:
    import grpc


class GrpcbinStub(Protocol):
    HeadersUnary: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.HeadersMessage]
    SpecificError: grpc.UnaryUnaryMultiCallable[grpcbin_pb2.SpecificErrorRequest, grpcbin_pb2.EmptyMessage]

    def __init__(self, channel: grpc.Channel) -> None:
        """Создать stub тестового сервиса."""


class AsyncGrpcbinStub(Protocol):
    HeadersUnary: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.EmptyMessage, grpcbin_pb2.HeadersMessage]
    SpecificError: grpc.aio.UnaryUnaryMultiCallable[grpcbin_pb2.SpecificErrorRequest, grpcbin_pb2.EmptyMessage]

    def __init__(self, channel: grpc.aio.Channel) -> None:
        """Создать stub тестового сервиса."""


class GRPCbinServiceClient(GRPCClient[GrpcbinStub]):
    """gRPC-клиент сервиса «GRPCBin»."""

    @property
    def stub_class(self) -> type[GrpcbinStub]:
        return cast("type[GrpcbinStub]", grpcbin_pb2_grpc.GRPCBinStub)

    def get_headers(self, metadata: MetadataType | None = None) -> GRPCResponse[grpcbin_pb2.HeadersMessage]:
        """Получить метаданные, которые сервис увидел в запросе.

        :param metadata: метаданные запроса
        :return: ответ с метаданными запроса
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.HeadersUnary, metadata)

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


class AsyncGRPCbinServiceClient(AsyncGRPCClient[AsyncGrpcbinStub]):
    """Асинхронный gRPC-клиент сервиса «GRPCBin»."""

    @property
    def stub_class(self) -> type[AsyncGrpcbinStub]:
        return cast("type[AsyncGrpcbinStub]", grpcbin_pb2_grpc.GRPCBinStub)

    async def get_headers(self, metadata: MetadataType | None = None) -> GRPCResponse[grpcbin_pb2.HeadersMessage]:
        """Получить метаданные, которые сервис увидел в запросе.

        :param metadata: метаданные запроса
        :return: ответ с метаданными запроса
        """
        return await self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.HeadersUnary, metadata)

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
