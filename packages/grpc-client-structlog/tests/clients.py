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
        """Create a test service stub."""


class AsyncEchoStub(Protocol):
    unary: grpc.aio.UnaryUnaryMultiCallable[Struct, Struct]
    server_stream: grpc.aio.UnaryStreamMultiCallable[Struct, Struct]
    client_stream: grpc.aio.StreamUnaryMultiCallable[Struct, Struct]
    bidirectional_stream: grpc.aio.StreamStreamMultiCallable[Struct, Struct]

    def __init__(self, channel: grpc.aio.Channel) -> None:
        """Create a test service stub."""


class EchoStub:
    """Test service stub built manually instead of generated from a proto file.

    The same class works over synchronous and asynchronous channels with different call types,
    so methods are not annotated with a specific multicallable type.
    """

    def __init__(self, channel: grpc.Channel | grpc.aio.Channel) -> None:
        """Create an instance with the supplied settings."""
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
    """Synchronous client for the test service."""

    @property
    def stub_class(self) -> type[SyncEchoStub]:
        return cast("type[SyncEchoStub]", EchoStub)

    def echo(self, msg: Struct, metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Send a message and receive the same message in response.

        :param msg: message to the server
        :param metadata: request metadata
        :returns: response with the same message
        """
        return self.send_unary_unary_request(msg, self.stub.unary, metadata)

    def download(self, msg: Struct, metadata: MetadataType | None = None) -> GRPCStreamResponse[Struct]:
        """Send a message and receive a message stream.

        :param msg: message to the server
        :param metadata: request metadata
        :returns: response message stream
        """
        return self.send_unary_stream_request(msg, self.stub.server_stream, metadata)

    def upload(self, messages: Iterator[Struct], metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Send a message stream and receive one response.

        :param messages: message stream
        :param metadata: request metadata
        :returns: response with the number of received messages
        """
        return self.send_stream_unary_request(messages, self.stub.client_stream, metadata)

    def chat(self, messages: Iterator[Struct], metadata: MetadataType | None = None) -> GRPCStreamResponse[Struct]:
        """Send a message stream and receive a stream in response.

        :param messages: message stream
        :param metadata: request metadata
        :returns: response message stream
        """
        return self.send_stream_stream_request(messages, self.stub.bidirectional_stream, metadata)


class AsyncEchoClient(AsyncGRPCClient[AsyncEchoStub]):
    """Asynchronous client for the test service."""

    @property
    def stub_class(self) -> type[AsyncEchoStub]:
        return cast("type[AsyncEchoStub]", EchoStub)

    async def echo(self, msg: Struct, metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Send a message and receive the same message in response.

        :param msg: message to the server
        :param metadata: request metadata
        :returns: response with the same message
        """
        return await self.send_unary_unary_request(msg, self.stub.unary, metadata)

    async def download(self, msg: Struct, metadata: MetadataType | None = None) -> AsyncGRPCStreamResponse[Struct]:
        """Send a message and receive a message stream.

        :param msg: message to the server
        :param metadata: request metadata
        :returns: response message stream
        """
        return await self.send_unary_stream_request(msg, self.stub.server_stream, metadata)

    async def upload(self, messages: Iterator[Struct], metadata: MetadataType | None = None) -> GRPCResponse[Struct]:
        """Send a message stream and receive one response.

        :param messages: message stream
        :param metadata: request metadata
        :returns: response with the number of received messages
        """
        return await self.send_stream_unary_request(messages, self.stub.client_stream, metadata)

    async def chat(
        self,
        messages: Iterator[Struct],
        metadata: MetadataType | None = None,
    ) -> AsyncGRPCStreamResponse[Struct]:
        """Send a message stream and receive a stream in response.

        :param messages: message stream
        :param metadata: request metadata
        :returns: response message stream
        """
        return await self.send_stream_stream_request(messages, self.stub.bidirectional_stream, metadata)
