from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from api.examples.examplepb import a_bit_of_everything_pb2_grpc as boe_pb2_grpc
from google.protobuf.empty_pb2 import Empty
from grpc_client import GRPCClient, GRPCResponse

if TYPE_CHECKING:
    import grpc
    from api.examples.sub.message_pb2 import StringMessage


class EverythingStub(Protocol):
    Echo: grpc.UnaryUnaryMultiCallable[StringMessage, StringMessage]
    ErrorWithDetails: grpc.UnaryUnaryMultiCallable[Empty, Empty]

    def __init__(self, channel: grpc.Channel) -> None:
        """Создать stub тестового сервиса."""


class ABitOfEverythingServiceClient(GRPCClient[EverythingStub]):
    """gRPC-клиент сервиса «A Bit Of Everything»."""

    @property
    def stub_class(self) -> type[EverythingStub]:
        return cast("type[EverythingStub]", boe_pb2_grpc.ABitOfEverythingServiceStub)

    def echo(self, msg: StringMessage) -> GRPCResponse[StringMessage]:
        """Отправить сообщение и получить его же в ответ.

        :param msg: сообщение серверу
        :return: ответ с тем же сообщением
        """
        return self.send_unary_unary_request(msg, self.stub.Echo)

    def error_with_details(self) -> GRPCResponse[Empty]:
        """Вызвать метод, отвечающий ошибкой с расширенными деталями.

        :return: ответ с ошибкой и деталями google.rpc.Status
        """
        return self.send_unary_unary_request(Empty(), self.stub.ErrorWithDetails)
