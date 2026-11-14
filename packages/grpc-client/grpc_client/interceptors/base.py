from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Literal, NamedTuple, cast, overload, override

import grpc

from grpc_client.metadata import merge_metadata

if TYPE_CHECKING:
    from grpc_client.types import MetadataItems

    SyncUnaryUnaryBase = grpc.UnaryUnaryClientInterceptor[object, object]
    SyncUnaryStreamBase = grpc.UnaryStreamClientInterceptor[object, object]
    SyncStreamUnaryBase = grpc.StreamUnaryClientInterceptor[object, object]
    SyncStreamStreamBase = grpc.StreamStreamClientInterceptor[object, object]
    AsyncUnaryUnaryBase = grpc.aio.UnaryUnaryClientInterceptor[object, object]
    AsyncUnaryStreamBase = grpc.aio.UnaryStreamClientInterceptor[object, object]
    AsyncStreamUnaryBase = grpc.aio.StreamUnaryClientInterceptor[object, object]
    AsyncStreamStreamBase = grpc.aio.StreamStreamClientInterceptor[object, object]
else:
    SyncUnaryUnaryBase = grpc.UnaryUnaryClientInterceptor
    SyncUnaryStreamBase = grpc.UnaryStreamClientInterceptor
    SyncStreamUnaryBase = grpc.StreamUnaryClientInterceptor
    SyncStreamStreamBase = grpc.StreamStreamClientInterceptor
    AsyncUnaryUnaryBase = grpc.aio.UnaryUnaryClientInterceptor
    AsyncUnaryStreamBase = grpc.aio.UnaryStreamClientInterceptor
    AsyncStreamUnaryBase = grpc.aio.StreamUnaryClientInterceptor
    AsyncStreamStreamBase = grpc.aio.StreamStreamClientInterceptor


type ContinuationType = Callable[[grpc.ClientCallDetails, object], object]
type StreamContinuation = Callable[[grpc.ClientCallDetails, object], object]
type AsyncUnaryContinuation = Callable[
    [grpc.aio.ClientCallDetails, object], grpc.aio.UnaryUnaryCall[object, object] | Awaitable[object]
]
type AsyncUnaryStreamContinuation = Callable[
    [grpc.aio.ClientCallDetails, object], grpc.aio.UnaryStreamCall[object, object] | Awaitable[object]
]
type AsyncStreamUnaryContinuation = Callable[
    [grpc.aio.ClientCallDetails, object], grpc.aio.StreamUnaryCall[object, object] | Awaitable[object]
]
type AsyncStreamStreamContinuation = Callable[
    [grpc.aio.ClientCallDetails, object], grpc.aio.StreamStreamCall[object, object] | Awaitable[object]
]


async def continue_async[T](continuation: object, details: grpc.aio.ClientCallDetails, request: object) -> T:
    """Call the grpc.aio continuation with its actual asynchronous signature.

    :param continuation: grpc.aio continuation function.
    :param details: call options.
    :param request: message or request stream.
    :return: running call object.
    """
    return await cast("Callable[[grpc.aio.ClientCallDetails, object], Awaitable[T]]", continuation)(details, request)


class ClientCallDetails(NamedTuple):
    """Call options passed through the interceptor chain."""

    method: str
    timeout: float | None
    metadata: MetadataItems | None
    credentials: grpc.CallCredentials | None
    wait_for_ready: bool | None
    compression: grpc.Compression | None


def with_metadata(
    call_details: object,
    metadata: MetadataItems,
) -> grpc.ClientCallDetails:
    """Create call options with extended metadata.

    :param call_details: original call options
    :param metadata: metadata appended at the end
    :return: new call options
    """
    return cast(
        "grpc.ClientCallDetails",
        ClientCallDetails(
            method=method_name(call_details),
            timeout=call_detail(call_details, "timeout", None),
            metadata=merge_metadata(call_detail(call_details, "metadata", None), metadata),
            credentials=call_detail(call_details, "credentials", None),
            wait_for_ready=call_detail(call_details, "wait_for_ready", None),
            compression=call_detail(call_details, "compression", None),
        ),
    )


@overload
def call_detail(call_details: object, name: Literal["method"], default: str) -> str | bytes: ...
@overload
def call_detail(call_details: object, name: Literal["metadata"], default: None) -> MetadataItems | None: ...
@overload
def call_detail(call_details: object, name: Literal["timeout"], default: None) -> float | None: ...
@overload
def call_detail(call_details: object, name: Literal["credentials"], default: None) -> grpc.CallCredentials | None: ...
@overload
def call_detail(call_details: object, name: Literal["wait_for_ready"], default: None) -> bool | None: ...
@overload
def call_detail(call_details: object, name: Literal["compression"], default: None) -> grpc.Compression | None: ...
def call_detail(call_details: object, name: str, default: object) -> object:
    """Read an optional grpcio call attribute."""
    return cast("object", getattr(call_details, name, default))


def method_name(call_details: object) -> str:
    """Get the full name of the called method.

    :param call_details: call options
    :return: method name as /package.Service/Method
    """
    method = call_detail(call_details, "method", "")
    return method.decode() if isinstance(method, bytes) else str(method)


def outcome_code(outcome: object) -> grpc.StatusCode | None:
    """Determine the status code of a completed call.

    grpcio call objects implement both `grpc.Call` and `grpc.RpcError`, so
    success and failure cannot be distinguished by object type, only by status code.

    :param outcome: object returned by the chain continuation
    :return: status code, or None if the object does not expose it
    """
    code = cast("Callable[[], object] | None", getattr(outcome, "code", None))
    if not callable(code):
        return None

    try:
        result = code()
    except Exception:  # noqa: BLE001 - an unavailable status must not break the call
        return None

    return result if isinstance(result, grpc.StatusCode) else None


class MetadataInterceptor(
    SyncUnaryUnaryBase,
    SyncUnaryStreamBase,
    SyncStreamUnaryBase,
    SyncStreamStreamBase,
    ABC,
):
    """Base synchronous interceptor that extends request metadata.

    Subclasses only need to implement `metadata_to_add()`: metadata will be added
    to all four call types.
    """

    @abstractmethod
    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Build metadata to add to a request.

        :param call_details: call options
        :return: key-value pairs appended to request metadata
        """

    @override
    def intercept_unary_unary(
        self,
        continuation: ContinuationType,
        client_call_details: grpc.ClientCallDetails,
        request: object,
    ) -> grpc.CallFuture[object]:
        return cast("grpc.CallFuture[object]", continuation(self._augment(client_call_details), request))

    @override
    def intercept_unary_stream(
        self,
        continuation: StreamContinuation,
        client_call_details: grpc.ClientCallDetails,
        request: object,
    ) -> grpc.CallIterator[object]:
        return cast("grpc.CallIterator[object]", continuation(self._augment(client_call_details), request))

    @override
    def intercept_stream_unary(
        self,
        continuation: ContinuationType,
        client_call_details: grpc.ClientCallDetails,
        request_iterator: Iterator[object],
    ) -> grpc.CallFuture[object]:
        return cast("grpc.CallFuture[object]", continuation(self._augment(client_call_details), request_iterator))

    @override
    def intercept_stream_stream(
        self,
        continuation: StreamContinuation,
        client_call_details: grpc.ClientCallDetails,
        request_iterator: Iterator[object],
    ) -> grpc.CallIterator[object]:
        return cast("grpc.CallIterator[object]", continuation(self._augment(client_call_details), request_iterator))

    def _augment(self, call_details: grpc.ClientCallDetails) -> grpc.ClientCallDetails:
        return with_metadata(call_details, self.metadata_to_add(call_details))


class AsyncMetadataInterceptor(
    AsyncUnaryUnaryBase,
    AsyncUnaryStreamBase,
    AsyncStreamUnaryBase,
    AsyncStreamStreamBase,
    ABC,
):
    """Base asynchronous interceptor that extends request metadata."""

    @abstractmethod
    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Build metadata to add to a request.

        :param call_details: call options
        :return: key-value pairs appended to request metadata
        """

    @override
    async def intercept_unary_unary(
        self,
        continuation: AsyncUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
        return await continue_async(continuation, await self._augment(client_call_details), request)

    @override
    async def intercept_unary_stream(
        self,
        continuation: AsyncUnaryStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        return await continue_async(continuation, await self._augment(client_call_details), request)

    @override
    async def intercept_stream_unary(
        self,
        continuation: AsyncStreamUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        return await continue_async(continuation, await self._augment(client_call_details), request_iterator)

    @override
    async def intercept_stream_stream(
        self,
        continuation: AsyncStreamStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.StreamStreamCall[object, object]:
        return await continue_async(continuation, await self._augment(client_call_details), request_iterator)

    async def _augment(self, call_details: grpc.aio.ClientCallDetails) -> grpc.aio.ClientCallDetails:
        added = await self.metadata_to_add(call_details)
        return aio_call_details(call_details, added)


def aio_call_details(
    call_details: object,
    metadata: MetadataItems,
) -> grpc.aio.ClientCallDetails:
    """Create asynchronous call options with extended metadata.

    :param call_details: original call options
    :param metadata: metadata appended at the end
    :return: new call options
    """
    merged = grpc.aio.Metadata()
    for key, value in call_detail(call_details, "metadata", None) or ():
        merged.add(key, value)
    for key, value in metadata:
        merged.add(key, value)

    return grpc.aio.ClientCallDetails(
        method=cast("str", call_detail(call_details, "method", "")),
        timeout=call_detail(call_details, "timeout", None),
        metadata=merged,
        credentials=call_detail(call_details, "credentials", None),
        wait_for_ready=call_detail(call_details, "wait_for_ready", None),
    )


def split_async_interceptor(interceptor: object) -> list[object]:
    """Split an asynchronous interceptor into separate grpc.aio interfaces.

    :param interceptor: original interceptor.
    :return: separate adapter for each supported call type.
    """
    implemented: list[object] = []
    if isinstance(interceptor, grpc.aio.UnaryUnaryClientInterceptor):
        implemented.append(_AsyncUnaryUnaryAdapter(cast("AsyncUnaryUnaryBase", interceptor)))
    if isinstance(interceptor, grpc.aio.UnaryStreamClientInterceptor):
        implemented.append(_AsyncUnaryStreamAdapter(cast("AsyncUnaryStreamBase", interceptor)))
    if isinstance(interceptor, grpc.aio.StreamUnaryClientInterceptor):
        implemented.append(_AsyncStreamUnaryAdapter(cast("AsyncStreamUnaryBase", interceptor)))
    if isinstance(interceptor, grpc.aio.StreamStreamClientInterceptor):
        implemented.append(_AsyncStreamStreamAdapter(cast("AsyncStreamStreamBase", interceptor)))
    return implemented if len(implemented) > 1 else [interceptor]


class _AsyncUnaryUnaryAdapter(AsyncUnaryUnaryBase):
    """Adapter for a single grpc.aio interface."""

    def __init__(self, impl: AsyncUnaryUnaryBase) -> None:
        """Store the interceptor implementation."""
        self.implementation = impl

    @override
    async def intercept_unary_unary(
        self, continuation: AsyncUnaryContinuation, client_call_details: grpc.aio.ClientCallDetails, request: object
    ) -> object:
        return await self.implementation.intercept_unary_unary(
            cast(
                "Callable[[grpc.aio.ClientCallDetails, object], grpc.aio.UnaryUnaryCall[object, object]]", continuation
            ),
            client_call_details,
            request,
        )


class _AsyncUnaryStreamAdapter(AsyncUnaryStreamBase):
    """Adapter for a single grpc.aio interface."""

    def __init__(self, impl: AsyncUnaryStreamBase) -> None:
        """Store the interceptor implementation."""
        self.implementation = impl

    @override
    async def intercept_unary_stream(
        self,
        continuation: AsyncUnaryStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        return await self.implementation.intercept_unary_stream(
            cast(
                "Callable[[grpc.aio.ClientCallDetails, object], grpc.aio.UnaryStreamCall[object, object]]", continuation
            ),
            client_call_details,
            request,
        )


class _AsyncStreamUnaryAdapter(AsyncStreamUnaryBase):
    """Adapter for a single grpc.aio interface."""

    def __init__(self, impl: AsyncStreamUnaryBase) -> None:
        """Store the interceptor implementation."""
        self.implementation = impl

    @override
    async def intercept_stream_unary(
        self,
        continuation: AsyncStreamUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        return await self.implementation.intercept_stream_unary(
            cast(
                "Callable[[grpc.aio.ClientCallDetails, object], grpc.aio.StreamUnaryCall[object, object]]", continuation
            ),
            client_call_details,
            request_iterator,
        )


class _AsyncStreamStreamAdapter(AsyncStreamStreamBase):
    """Adapter for a single grpc.aio interface."""

    def __init__(self, impl: AsyncStreamStreamBase) -> None:
        """Store the interceptor implementation."""
        self.implementation = impl

    @override
    async def intercept_stream_stream(
        self,
        continuation: AsyncStreamStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.StreamStreamCall[object, object]:
        return await self.implementation.intercept_stream_stream(
            cast(
                "Callable[[grpc.aio.ClientCallDetails, object], grpc.aio.StreamStreamCall[object, object]]",
                continuation,
            ),
            client_call_details,
            request_iterator,
        )
