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
        """Create a test service stub."""


class ABitOfEverythingServiceClient(GRPCClient[EverythingStub]):
    """gRPC client for the A Bit Of Everything service."""

    @property
    def stub_class(self) -> type[EverythingStub]:
        return cast("type[EverythingStub]", boe_pb2_grpc.ABitOfEverythingServiceStub)

    def echo(self, msg: StringMessage) -> GRPCResponse[StringMessage]:
        """Send a message and receive the same message in response.

        :param msg: message to the server
        :return: response with the same message
        """
        return self.send_unary_unary_request(msg, self.stub.Echo)

    def error_with_details(self) -> GRPCResponse[Empty]:
        """Call a method that returns an error with rich details.

        :return: response with an error and google.rpc.Status details
        """
        return self.send_unary_unary_request(Empty(), self.stub.ErrorWithDetails)
