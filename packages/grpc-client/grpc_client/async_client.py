from __future__ import annotations

import asyncio
from abc import ABCMeta
from typing import TYPE_CHECKING, Protocol, Self, cast, override, runtime_checkable

import grpc

from .base_client import BaseGRPCClient, ClientOption, TAsyncStub, TRequest, TResponse
from .interceptors.base import split_async_interceptor
from .metadata import aio_metadata_items
from .response import AsyncGRPCStreamResponse, GRPCResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from types import TracebackType

    from .call_options import CallOptions
    from .types import MetadataType


@runtime_checkable
class _Drainable(Protocol):
    async def drain(self) -> None: ...


class _AsyncChannelFactory(Protocol):
    def __call__(
        self,
        target: str,
        credentials: grpc.ChannelCredentials | None = None,
        *,
        options: object = None,
        compression: grpc.Compression | None = None,
        interceptors: object = None,
    ) -> grpc.aio.Channel: ...


class AsyncGRPCClient(BaseGRPCClient[TAsyncStub], metaclass=ABCMeta):
    """Base class for asynchronous gRPC clients.

    Subclasses declare `stub_class` and wrap service methods in `send_*_request` calls.
    Create a client from a service address or an existing channel. A channel created
    by the client closes with it; externally supplied channels remain the caller's responsibility.

    Interceptors are accepted only with an address: `grpc.aio` allows setting them
    only when creating a channel.
    """

    def __init__(self, target: str | grpc.aio.Channel, *options: ClientOption) -> None:
        """Initialize the object.

        :param target: service address such as `example.com:443` or an existing channel
        :param options: client options from `grpc_client.options`
        """
        super().__init__()
        self._apply(options)

        self._owns_channel = not isinstance(target, grpc.aio.Channel)
        if self._owns_channel:
            self._channel = self._create_channel(cast("str", target))
        else:
            # grpc.aio accepts interceptors only when creating a channel: there is no
            # asynchronous equivalent of grpc.intercept_channel() in the public API.
            # Silently swallowing these would disable authentication and logging.
            if self._interceptors:
                msg = (
                    "Интерцепторы нельзя добавить к готовому асинхронному каналу: "
                    "создайте канал через grpc.aio.insecure_channel(..., interceptors=[...]) "
                    "либо клиент через from_addr()"
                )
                raise ValueError(msg)
            self._channel = cast("grpc.aio.Channel", target)

        self.stub: TAsyncStub = self.stub_class(self._channel)

    @override
    def add_interceptor(self, interceptor: object) -> None:
        """Add an interceptor for all supported call types.

        :param interceptor: asynchronous grpcio interceptor.
        """
        for item in split_async_interceptor(interceptor):
            super().add_interceptor(item)

    @classmethod
    def from_addr(cls, addr: str, *options: ClientOption) -> Self:
        """Create a client using a service address.

        :param addr: service address such as `example.com:443`
        :param options: client options from `grpc_client.options`
        :return: asynchronous gRPC client
        """
        return cls(addr, *options)

    @classmethod
    def from_channel(cls, channel: grpc.aio.Channel, *options: ClientOption) -> Self:
        """Create a client over an existing channel.

        The client does not close the channel: its lifecycle is managed by the caller.

        :param channel: existing channel
        :param options: client options from `grpc_client.options`
        :return: asynchronous gRPC client
        """
        return cls(channel, *options)

    async def __aenter__(self) -> Self:
        """Return the client for an asynchronous with block."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the channel owned by the client."""
        await self.close()

    @property
    def channel(self) -> grpc.aio.Channel:
        """Channel used to send requests."""
        return self._channel

    async def close(self, grace: float | None = None) -> None:
        """Close the channel if it was created by the client.

        Wait for interceptors with deferred logging: the final stream log is written in a separate
        task. Draining also runs after channel closure, as unfinished streams are interrupted
        at that moment, and their logging tasks appear only then.

        :param grace: time in seconds allowed for active calls to finish
        """
        await self._drain_interceptors()

        if self._owns_channel:
            await self._channel.close(grace)

        await self._drain_interceptors()

    async def _drain_interceptors(self) -> None:
        """Wait for interceptors that write logs in deferred tasks.

        An interceptor may have been split into call type adapters, so drain
        the implementation itself, once each.
        """
        # The call completion callback does not create the logging task immediately; allow the event loop
        # advance, otherwise draining misses the newly interrupted stream.
        await asyncio.sleep(0)

        drained: set[int] = set()

        for interceptor in self._interceptors:
            target = cast("object", getattr(interceptor, "implementation", interceptor))
            if id(target) in drained:
                continue

            drained.add(id(target))
            if isinstance(target, _Drainable):
                await target.drain()

    async def send_unary_unary_request(
        self,
        msg: TRequest,
        method: grpc.aio.UnaryUnaryMultiCallable[TRequest, TResponse],
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
        call = method(msg, **self._call_kwargs(self._call_options(metadata, options)))
        return await self._unary_response(call)

    async def send_stream_unary_request(
        self,
        stream: AsyncIterator[TRequest] | Iterator[TRequest],
        method: grpc.aio.StreamUnaryMultiCallable[TRequest, TResponse],
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
        call = method(stream, **self._call_kwargs(self._call_options(metadata, options)))
        return await self._unary_response(call)

    async def send_unary_stream_request(
        self,
        msg: TRequest,
        method: grpc.aio.UnaryStreamMultiCallable[TRequest, TResponse],
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> AsyncGRPCStreamResponse[TResponse]:
        """Send a request and receive a stream of response messages.

        :param msg: request message
        :param method: service method from `self.stub`
        :param metadata: request metadata
        :param options: call options that override client settings
        :return: response message stream
        """
        call = method(msg, **self._call_kwargs(self._call_options(metadata, options)))
        return AsyncGRPCStreamResponse(cast("grpc.aio.Call", call))

    async def send_stream_stream_request(
        self,
        stream: AsyncIterator[TRequest] | Iterator[TRequest],
        method: grpc.aio.StreamStreamMultiCallable[TRequest, TResponse],
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> AsyncGRPCStreamResponse[TResponse]:
        """Send a message stream and receive a stream of response messages.

        :param stream: request message iterator
        :param method: service method from `self.stub`
        :param metadata: request metadata
        :param options: call options that override client settings
        :return: response message stream
        """
        call = method(stream, **self._call_kwargs(self._call_options(metadata, options)))
        return AsyncGRPCStreamResponse(cast("grpc.aio.Call", call))

    def _create_channel(self, addr: str) -> grpc.aio.Channel:
        if self.secure:
            return cast("_AsyncChannelFactory", grpc.aio.secure_channel)(
                addr,
                self._credentials(),
                options=self.channel_options or None,
                compression=self.compression,
                interceptors=self._interceptors or None,
            )
        return cast("_AsyncChannelFactory", grpc.aio.insecure_channel)(
            addr,
            options=self.channel_options or None,
            compression=self.compression,
            interceptors=self._interceptors or None,
        )

    @staticmethod
    async def _unary_response[R, T](
        call: grpc.aio.UnaryUnaryCall[R, T] | grpc.aio.StreamUnaryCall[R, T],
    ) -> GRPCResponse[T]:
        """Wait for the unary call to finish and assemble the response.

        :param call: running call
        :return: request response
        """
        try:
            message = await call
        except grpc.aio.AioRpcError as error:
            return GRPCResponse.from_error(error)

        return GRPCResponse(
            message=message,
            status_code=cast("grpc.StatusCode | None", await call.code()) or grpc.StatusCode.UNKNOWN,
            details=await call.details() or "",
            initial_metadata=aio_metadata_items(await call.initial_metadata()),
            trailing_metadata=aio_metadata_items(await call.trailing_metadata()),
        )
