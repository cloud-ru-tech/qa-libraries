import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from types import TracebackType
from typing import Self, TypedDict, TypeVar, Unpack, cast

import grpc

from .exceptions import (
    MessageUndefinedError,
    ResponseStatusError,
    StreamConsumedError,
    StreamNotConsumedError,
)
from .metadata import Metadata, aio_metadata_items
from .status import ErrorStatus, error_status_from_metadata
from .types import MetadataItems

# Response message type (Message from a generated pb2 module).
TMsg = TypeVar("TMsg")

# Parsed response message type.
TResult = TypeVar("TResult")


class ResponseOptions(TypedDict, total=False):
    """Additional data about a completed call."""

    initial_metadata: MetadataItems | None
    trailing_metadata: MetadataItems | None
    error: grpc.RpcError | None


class GRPCResponse[TMsg]:
    """Response to a unary gRPC request."""

    __slots__ = ("_details", "_error", "_initial_metadata", "_message", "_status_code", "_trailing_metadata")

    def __init__(
        self,
        *,
        message: TMsg | None,
        status_code: grpc.StatusCode,
        details: str,
        **options: Unpack[ResponseOptions],
    ) -> None:
        """Create an instance with the supplied settings."""
        self._message = message
        self._status_code = status_code
        self._details = details
        self._initial_metadata = Metadata(options.get("initial_metadata"))
        self._trailing_metadata = Metadata(options.get("trailing_metadata"))
        self._error = options.get("error")

    @classmethod
    def from_call(cls, message: TMsg | None, call: grpc.Call) -> Self:
        """Build a response from a completed call.

        :param message: response message
        :param call: gRPC call object
        :return: request response
        """
        return cls(
            message=message,
            status_code=cast("grpc.StatusCode | None", call.code()) or grpc.StatusCode.UNKNOWN,
            details=call.details() or "",
            initial_metadata=_safe_metadata(call.initial_metadata),
            trailing_metadata=_safe_metadata(call.trailing_metadata),
        )

    @classmethod
    def from_error(cls, error: grpc.RpcError, message: TMsg | None = None) -> Self:
        """Build a response from a call error.

        :param error: gRPC error implementing the `grpc.Call` interface
        :param message: message if one is still available, for example part of a stream,
            received before the error
        :return: request response
        """
        call = cast("grpc.Call", error)
        return cls(
            message=message,
            status_code=cast("grpc.StatusCode | None", call.code()) or grpc.StatusCode.UNKNOWN,
            details=call.details() or "",
            initial_metadata=_safe_metadata(call.initial_metadata),
            trailing_metadata=_safe_metadata(call.trailing_metadata),
            error=error,
        )

    @property
    def status_code(self) -> grpc.StatusCode:
        """Server response status code."""
        return self._status_code

    @property
    def details(self) -> str:
        """Additional response information, usually populated for unsuccessful statuses."""
        return self._details

    @property
    def ok(self) -> bool:
        """Whether the request succeeded."""
        return self._status_code is grpc.StatusCode.OK

    @property
    def initial_metadata(self) -> Metadata:
        """Metadata received before the response body. Closest equivalent to HTTP headers."""
        return self._initial_metadata

    @property
    def trailing_metadata(self) -> Metadata:
        """Metadata received after the response body. Services send error details here."""
        return self._trailing_metadata

    @property
    def metadata(self) -> Metadata:
        """Alias for `trailing_metadata`."""
        return self._trailing_metadata

    @property
    def error(self) -> grpc.RpcError | None:
        """Original gRPC error if the request failed."""
        return self._error

    @property
    def error_status(self) -> ErrorStatus | None:
        """Rich error status sent by the service in google.rpc.Status."""
        return error_status_from_metadata(self._trailing_metadata)

    def raise_for_status(self) -> Self:
        """Raise an exception if the request failed.

        :raises ResponseStatusError: if the response code is not OK
        :return: the response itself for chaining
        """
        if not self.ok:
            raise ResponseStatusError(self._status_code, self._details)
        return self

    def message(self) -> TMsg:
        """Get the response message.

        :raises MessageUndefinedError: if the response message is absent
        :return: response message
        """
        if self._message is None:
            raise MessageUndefinedError(self._status_code, self._details)
        return self._message

    def with_parser(self, parser: Callable[[TMsg], TResult]) -> "GRPCResponseWithParser[TMsg, TResult]":
        """Add a response message transformation function to the response.

        :param parser: response message transformation function
        :return: response with a message parser
        """
        return GRPCResponseWithParser(self, parser)


class GRPCResponseWithParser[TMsg, TResult]:
    """gRPC server response with a response message parser."""

    __slots__ = ("_parser", "_response")

    def __init__(self, response: GRPCResponse[TMsg], parser: Callable[[TMsg], TResult]) -> None:
        """Create an instance with the supplied settings."""
        self._response = response
        self._parser = parser

    @property
    def status_code(self) -> grpc.StatusCode:
        """Server response status code."""
        return self._response.status_code

    @property
    def details(self) -> str:
        """Additional response information, usually populated for unsuccessful statuses."""
        return self._response.details

    @property
    def ok(self) -> bool:
        """Whether the request succeeded."""
        return self._response.ok

    @property
    def initial_metadata(self) -> Metadata:
        """Metadata received before the response body."""
        return self._response.initial_metadata

    @property
    def trailing_metadata(self) -> Metadata:
        """Metadata received after the response body."""
        return self._response.trailing_metadata

    @property
    def metadata(self) -> Metadata:
        """Alias for `trailing_metadata`."""
        return self._response.metadata

    @property
    def error(self) -> grpc.RpcError | None:
        """Original gRPC error if the request failed."""
        return self._response.error

    @property
    def error_status(self) -> ErrorStatus | None:
        """Rich error status sent by the service in google.rpc.Status."""
        return self._response.error_status

    def raise_for_status(self) -> Self:
        """Raise an exception if the request failed.

        :raises ResponseStatusError: if the response code is not OK
        :return: the response itself for chaining
        """
        self._response.raise_for_status()
        return self

    def message(self) -> TMsg:
        """Get the response message.

        :raises MessageUndefinedError: if the response message is absent
        :return: response message
        """
        return self._response.message()

    def parse(self) -> TResult:
        """Parse the response message.

        :raises MessageUndefinedError: if the response message is absent
        :return: parser result
        """
        return self._parser(self.message())


class GRPCStreamResponse[TMsg]:
    """Response to a streaming gRPC request.

    Messages are read lazily as they arrive from the server and are not buffered.
    The server reports final status and trailing metadata only after stream completion,
    so they remain unavailable until reading finishes.

    A stream keeps its call open and must either be fully read or closed.
    The easiest use is as a context manager: an unfinished call is cancelled on exit.
    """

    __slots__ = ("_call", "_consumed", "_iterator")

    def __init__(self, call: grpc.Call) -> None:
        """Create an instance with the supplied settings."""
        self._call = call
        self._iterator = cast("Iterator[TMsg]", call)
        self._consumed = False

    def __iter__(self) -> Iterator[TMsg]:
        """Get an iterator of values."""
        if self._consumed:
            raise StreamConsumedError

        # A stream is considered consumed only when it actually ends: when iteration exits
        # early, the call is still active and must be cancelled.
        try:
            yield from self._iterator
        except grpc.RpcError:
            self._consumed = True
            raise

        self._consumed = True

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
        self.cancel()

    @property
    def initial_metadata(self) -> Metadata:
        """Metadata received before the response body."""
        return Metadata(_safe_metadata(self._call.initial_metadata))

    @property
    def trailing_metadata(self) -> Metadata:
        """Metadata received after stream completion.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        self._ensure_consumed("trailing_metadata")
        return Metadata(_safe_metadata(self._call.trailing_metadata))

    @property
    def status_code(self) -> grpc.StatusCode:
        """Final stream status code.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        self._ensure_consumed("status_code")
        return cast("grpc.StatusCode | None", self._call.code()) or grpc.StatusCode.UNKNOWN

    @property
    def details(self) -> str:
        """Additional information about stream completion.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        self._ensure_consumed("details")
        return self._call.details() or ""

    @property
    def ok(self) -> bool:
        """Whether the stream succeeded.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        return self.status_code is grpc.StatusCode.OK

    def cancel(self) -> None:
        """Cancel the call if it has not finished yet."""
        if not self._consumed:
            cast("Callable[[], bool]", self._call.cancel)()
            self._consumed = True

    def collect(self, limit: int | None = None) -> GRPCResponse[list[TMsg]]:
        """Read the entire stream and collect messages in a list.

        Server errors are converted into responses with matching status codes rather than raised.

        :param limit: maximum message count; the call is cancelled when the limit is reached,
            `0` means read nothing and cancel the call immediately
        :raises StreamConsumedError: if the stream has already been read
        :raises ValueError: if the limit is negative
        :return: response with a list of received messages
        """
        if self._consumed:
            raise StreamConsumedError
        _check_limit(limit)

        messages: list[TMsg] = []
        if limit == 0:
            self.cancel()
            return GRPCResponse.from_call(messages, self._call)

        try:
            for message in self:
                messages.append(message)
                if limit is not None and len(messages) >= limit:
                    self.cancel()
                    break
        except grpc.RpcError as error:
            # Messages received before the error are still useful: they show
            # where the stream was interrupted.
            return GRPCResponse.from_error(error, messages)

        return GRPCResponse.from_call(messages, self._call)

    def _ensure_consumed(self, attribute: str) -> None:
        if not self._consumed:
            raise StreamNotConsumedError(attribute)


class AsyncGRPCStreamResponse[TMsg]:
    """Response to a streaming gRPC request in the asynchronous client.

    Behaves like `GRPCStreamResponse`, but is read asynchronously.
    """

    __slots__ = ("_call", "_cancelled_by_client", "_consumed", "_iterator")

    def __init__(self, call: grpc.aio.Call) -> None:
        """Create an instance with the supplied settings."""
        self._call = call
        self._iterator = cast("AsyncIterator[TMsg]", call)
        self._consumed = False
        self._cancelled_by_client = False

    async def __aiter__(self) -> AsyncIterator[TMsg]:
        """Get an asynchronous message iterator."""
        if self._consumed:
            raise StreamConsumedError

        # A stream is considered consumed only when it actually ends: when iteration exits
        # early, the call is still active and must be cancelled.
        try:
            async for message in self._iterator:
                yield message
        except grpc.aio.AioRpcError:
            self._consumed = True
            raise
        except asyncio.CancelledError:
            # Propagate cancellation, but make the stream terminal: cancel the call as well,
            # otherwise it would remain pending and its status would be unavailable.
            self._cancelled_by_client = bool(self._call.cancel())
            self._consumed = True
            raise

        self._consumed = True

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
        self.cancel()

    async def initial_metadata(self) -> Metadata:
        """Get metadata received before the response body."""
        return Metadata(aio_metadata_items(await self._call.initial_metadata()))

    async def trailing_metadata(self) -> Metadata:
        """Get metadata received after stream completion.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        self._ensure_consumed("trailing_metadata")
        return Metadata(aio_metadata_items(await self._call.trailing_metadata()))

    async def status_code(self) -> grpc.StatusCode:
        """Get the final stream status code.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        self._ensure_consumed("status_code")
        return cast("grpc.StatusCode | None", await self._call.code()) or grpc.StatusCode.UNKNOWN

    async def details(self) -> str:
        """Get additional stream completion information.

        :raises StreamNotConsumedError: if the stream has not been fully read
        """
        self._ensure_consumed("details")
        return await self._call.details() or ""

    def cancel(self) -> None:
        """Cancel the call if it has not finished yet."""
        if not self._consumed:
            # cancel() returns False if the call already completed: its actual
            # status takes priority and must not be replaced with CANCELLED.
            self._cancelled_by_client = bool(self._call.cancel())
            self._consumed = True

    async def collect(self, limit: int | None = None) -> GRPCResponse[list[TMsg]]:
        """Read the entire stream and collect messages in a list.

        Server errors are converted into responses with matching status codes rather than raised.

        :param limit: maximum message count; the call is cancelled when the limit is reached,
            `0` means read nothing and cancel the call immediately
        :raises StreamConsumedError: if the stream has already been read
        :raises ValueError: if the limit is negative
        :return: response with a list of received messages
        """
        if self._consumed:
            raise StreamConsumedError
        _check_limit(limit)

        messages: list[TMsg] = []
        if limit == 0:
            self.cancel()
            return await self._response_with(messages)

        try:
            async for message in self:
                messages.append(message)
                if limit is not None and len(messages) >= limit:
                    self.cancel()
                    break
        except grpc.aio.AioRpcError as error:
            # Messages received before the error are still useful.
            return GRPCResponse.from_error(error, messages)

        return await self._response_with(messages)

    async def _response_with(self, messages: list[TMsg]) -> GRPCResponse[list[TMsg]]:
        """Build a response from the actual call state.

        If the client itself cancelled the stream due to a reached or zero limit, the status
        is known in advance. Reading it from a cancelled call would raise
        `CancelledError`, which must not be caught here because that would also swallow cancellation
        of the calling task, breaking `asyncio.timeout` and graceful application shutdown.
        """
        if self._cancelled_by_client:
            return GRPCResponse(message=messages, status_code=grpc.StatusCode.CANCELLED, details="")

        return GRPCResponse(
            message=messages,
            status_code=cast("grpc.StatusCode | None", await self._call.code()) or grpc.StatusCode.UNKNOWN,
            details=await self._call.details() or "",
            initial_metadata=aio_metadata_items(await self._call.initial_metadata()),
            trailing_metadata=aio_metadata_items(await self._call.trailing_metadata()),
        )

    def _ensure_consumed(self, attribute: str) -> None:
        if not self._consumed:
            raise StreamNotConsumedError(attribute)


def _check_limit(limit: int | None) -> None:
    """Check the limit on the number of messages to read.

    :param limit: maximum message count
    :raises ValueError: if the limit is negative
    """
    if limit is not None and limit < 0:
        message = f"Ограничение на количество сообщений не может быть отрицательным, получено {limit}"
        raise ValueError(message)


def _safe_metadata(getter: Callable[[], MetadataItems | None]) -> MetadataItems:
    """Read call metadata without failing for implementations that do not expose it.

    :param getter: call method returning metadata
    :return: metadata or an empty sequence
    """
    try:
        return getter() or ()
    except (AttributeError, ValueError, grpc.RpcError):
        return ()
