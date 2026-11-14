from __future__ import annotations

from abc import ABCMeta
from typing import TYPE_CHECKING, Self, cast

import grpc

from .base_client import BaseGRPCClient, ClientInterceptorTypes, ClientOption, TRequest, TResponse, TStub
from .response import GRPCResponse, GRPCStreamResponse

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

    from .call_options import CallOptions
    from .types import MetadataType


class GRPCClient(BaseGRPCClient[TStub], metaclass=ABCMeta):
    """Base class for synchronous gRPC clients.

    Create a client from a service address or an existing channel. A channel created
    by the client closes with it; externally supplied channels remain the caller's responsibility.
    """

    def __init__(self, target: str | grpc.Channel, *options: ClientOption) -> None:
        """Initialize the object.

        :param target: service address such as `example.com:443` or an existing channel
        :param options: client options from `grpc_client.options`
        """
        super().__init__()
        self._apply(options)

        self._owns_channel = not isinstance(target, grpc.Channel)
        channel = self._create_channel(cast("str", target)) if self._owns_channel else cast("grpc.Channel", target)

        self._channel = (
            grpc.intercept_channel(channel, *cast("list[ClientInterceptorTypes]", self._interceptors))
            if self._interceptors
            else channel
        )
        self.stub: TStub = self.stub_class(self._channel)

    @classmethod
    def from_addr(cls, addr: str, *options: ClientOption) -> Self:
        """Create a client using a service address.

        :param addr: service address such as `example.com:443`
        :param options: client options from `grpc_client.options`
        :return: gRPC client
        """
        return cls(addr, *options)

    @classmethod
    def from_channel(cls, channel: grpc.Channel, *options: ClientOption) -> Self:
        """Create a client over an existing channel.

        The client does not close the channel: its lifecycle is managed by the caller.

        :param channel: existing channel
        :param options: client options from `grpc_client.options`
        :return: gRPC client
        """
        return cls(channel, *options)

    def __enter__(self) -> Self:
        """Return the client for a with block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the channel owned by the client."""
        self.close()

    @property
    def channel(self) -> grpc.Channel:
        """Channel used to send requests."""
        return self._channel

    def close(self) -> None:
        """Close the channel if it was created by the client."""
        if self._owns_channel:
            self._channel.close()

    def send_unary_unary_request(
        self,
        msg: TRequest,
        method: grpc.UnaryUnaryMultiCallable[TRequest, TResponse],
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[TResponse]:
        """Send a unary request and wait for the response.

        :param msg: request message
        :param method: service method from `self.stub`
        :param metadata: request metadata
        :param options: call options that override client settings
        :return: request response
        """
        call_options = self._call_options(metadata, options)
        try:
            message, call = method.with_call(msg, **self._call_kwargs(call_options))
        except grpc.RpcError as error:
            return GRPCResponse[TResponse].from_error(self._call_error(error))

        return GRPCResponse.from_call(message, call)

    def send_stream_unary_request(
        self,
        stream: Iterator[TRequest],
        method: grpc.StreamUnaryMultiCallable[TRequest, TResponse],
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[TResponse]:
        """Send a message stream and wait for one response.

        :param stream: request message iterator
        :param method: service method from `self.stub`
        :param metadata: request metadata
        :param options: call options that override client settings
        :return: request response
        """
        call_options = self._call_options(metadata, options)
        try:
            message, call = method.with_call(stream, **self._call_kwargs(call_options))
        except grpc.RpcError as error:
            return GRPCResponse[TResponse].from_error(self._call_error(error))

        return GRPCResponse.from_call(message, call)

    def send_unary_stream_request(
        self,
        msg: TRequest,
        method: grpc.UnaryStreamMultiCallable[TRequest, TResponse],
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCStreamResponse[TResponse]:
        """Send a request and receive a stream of response messages.

        Messages are read lazily. To receive them as a list with the final status,
        call `collect()` on the returned object.

        :param msg: request message
        :param method: service method from `self.stub`
        :param metadata: request metadata
        :param options: call options that override client settings
        :return: response message stream
        """
        call_options = self._call_options(metadata, options)
        call = method(msg, **self._call_kwargs(call_options))
        return GRPCStreamResponse(cast("grpc.Call", call))

    def send_stream_stream_request(
        self,
        stream: Iterator[TRequest],
        method: grpc.StreamStreamMultiCallable[TRequest, TResponse],
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCStreamResponse[TResponse]:
        """Send a message stream and receive a stream of response messages.

        :param stream: request message iterator
        :param method: service method from `self.stub`
        :param metadata: request metadata
        :param options: call options that override client settings
        :return: response message stream
        """
        call_options = self._call_options(metadata, options)
        call = method(stream, **self._call_kwargs(call_options))
        return GRPCStreamResponse(cast("grpc.Call", call))

    def _create_channel(self, addr: str) -> grpc.Channel:
        if self.secure:
            return grpc.secure_channel(
                addr,
                self._credentials(),
                options=self.channel_options or None,
                compression=self.compression,
            )
        return grpc.insecure_channel(
            addr,
            options=self.channel_options or None,
            compression=self.compression,
        )

    @staticmethod
    def _call_error(error: grpc.RpcError) -> grpc.RpcError:
        """Convert a call error into a response.

        Errors not implementing `grpc.Call` are propagated: they cannot provide
        neither status code nor metadata.

        :param error: gRPC error
        :return: response without a message and with an error status code
        """
        if not isinstance(cast("object", error), grpc.Call):
            raise error
        return error
