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
        """Create a test service stub."""


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
        """Create a test service stub."""


class GRPCbinServiceClient(GRPCClient[GrpcbinStub]):
    """gRPC client for the GRPCBin service."""

    @property
    def stub_class(self) -> type[GrpcbinStub]:
        return cast("type[GrpcbinStub]", grpcbin_pb2_grpc.GRPCBinStub)

    def dummy_unary(
        self,
        msg: grpcbin_pb2.DummyMessage,
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Send a message and receive the same message in response.

        :param msg: message to the server
        :param metadata: request metadata
        :param options: call options
        :return: response with the same message
        """
        return self.send_unary_unary_request(msg, self.stub.DummyUnary, metadata, options)

    def empty(self, options: CallOptions | None = None) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Call a method that returns an empty message.

        :param options: call options
        :return: response with an empty message
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.Empty, options=options)

    def specific_error(self, code: int, reason: str) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Ask the service to return the specified error.

        :param code: gRPC error code
        :param reason: error text
        :return: response with the requested error
        """
        return self.send_unary_unary_request(
            grpcbin_pb2.SpecificErrorRequest(code=code, reason=reason),
            self.stub.SpecificError,
        )

    def no_response(self, options: CallOptions | None = None) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Call a method that never responds.

        :param options: call options
        :return: response that the service will never send
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.NoResponseUnary, options=options)

    def send_client_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Send a message stream and receive one response.

        :param messages: message stream
        :return: response with a server message
        """
        return self.send_stream_unary_request(messages, self.stub.DummyClientStream)

    def send_server_stream(
        self,
        msg: grpcbin_pb2.DummyMessage,
        options: CallOptions | None = None,
    ) -> GRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Send a message and receive a message stream.

        :param msg: message to the server
        :param options: call options
        :return: response message stream
        """
        return self.send_unary_stream_request(msg, self.stub.DummyServerStream, options=options)

    def send_bidirectional_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
        options: CallOptions | None = None,
    ) -> GRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Send a message stream and receive a stream in response.

        :param messages: message stream
        :param options: call options
        :return: response message stream
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
        """Get the metadata received by the service in the request.

        :param metadata: request metadata
        :param options: call options
        :return: response with request metadata
        """
        return self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.HeadersUnary, metadata, options)


class AsyncGRPCbinServiceClient(AsyncGRPCClient[AsyncGrpcbinStub]):
    """Asynchronous gRPC client for the GRPCBin service."""

    @property
    def stub_class(self) -> type[AsyncGrpcbinStub]:
        return cast("type[AsyncGrpcbinStub]", grpcbin_pb2_grpc.GRPCBinStub)

    async def dummy_unary(
        self,
        msg: grpcbin_pb2.DummyMessage,
        metadata: MetadataType | None = None,
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Send a message and receive the same message in response.

        :param msg: message to the server
        :param metadata: request metadata
        :return: response with the same message
        """
        return await self.send_unary_unary_request(msg, self.stub.DummyUnary, metadata)

    async def specific_error(self, code: int, reason: str) -> GRPCResponse[grpcbin_pb2.EmptyMessage]:
        """Ask the service to return the specified error.

        :param code: gRPC error code
        :param reason: error text
        :return: response with the requested error
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
        """Send a message and receive a message stream.

        :param msg: message to the server
        :param options: call options
        :return: response message stream
        """
        return await self.send_unary_stream_request(msg, self.stub.DummyServerStream, options=options)

    async def send_client_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
    ) -> GRPCResponse[grpcbin_pb2.DummyMessage]:
        """Send a message stream and receive one response.

        :param messages: message stream
        :return: response with a server message
        """
        return await self.send_stream_unary_request(messages, self.stub.DummyClientStream)

    async def send_bidirectional_stream(
        self,
        messages: Iterator[grpcbin_pb2.DummyMessage],
    ) -> AsyncGRPCStreamResponse[grpcbin_pb2.DummyMessage]:
        """Send a message stream and receive a stream in response.

        :param messages: message stream
        :return: response message stream
        """
        return await self.send_stream_stream_request(messages, self.stub.DummyBidirectionalStreamStream)

    async def get_headers(self, metadata: MetadataType | None = None) -> GRPCResponse[grpcbin_pb2.HeadersMessage]:
        """Get the metadata received by the service in the request.

        :param metadata: request metadata
        :return: response with request metadata
        """
        return await self.send_unary_unary_request(grpcbin_pb2.EmptyMessage(), self.stub.HeadersUnary, metadata)
