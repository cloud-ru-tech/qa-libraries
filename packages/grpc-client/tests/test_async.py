import asyncio
import io
import logging
from collections.abc import AsyncIterable, Iterable, Iterator
from typing import cast, override
from uuid import uuid4

import grpc
import pytest
from api import grpcbin_pb2
from grpc_client import (
    AsyncGRPCStreamResponse,
    BaseGRPCClient,
    CallOptions,
    MetadataItems,
    StreamConsumedError,
    options,
)
from grpc_client.interceptors import (
    AsyncAuthInterceptor,
    AsyncAutogenerateRequestIdInterceptor,
    AsyncLoggingInterceptor,
)
from grpc_client.interceptors.base import (
    AsyncMetadataInterceptor,
    AsyncStreamStreamContinuation,
    AsyncStreamUnaryContinuation,
    AsyncUnaryContinuation,
    AsyncUnaryStreamContinuation,
    AsyncUnaryUnaryBase,
    continue_async,
    split_async_interceptor,
)

from .assertions import assert_that
from .clients import AsyncGRPCbinServiceClient
from .fakes import (
    FakeAsyncAuth,
    FakeAsyncCallbackStreamCall,
    FakeAsyncContinuation,
    FakeAsyncStreamCall,
    FakeAuth,
    FakeFailingAsyncStreamCall,
    fake_aio_call_details,
)
from .support import code_number

STREAM_MESSAGES_COUNT = 10


async def test_returns_ok_status_for_unary_request(async_grpcbin_client: AsyncGRPCbinServiceClient) -> None:
    """A successful asynchronous request finishes with status OK."""
    response = await async_grpcbin_client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="перевозка"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_returns_echoed_message(async_grpcbin_client: AsyncGRPCbinServiceClient) -> None:
    """The service returns the sent message."""
    sent_value = "маршрутный лист"

    response = await async_grpcbin_client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=sent_value))

    assert_that(response.message().f_string).is_equal_to(sent_value)


async def test_returns_requested_error_code(async_grpcbin_client: AsyncGRPCbinServiceClient) -> None:
    """The service responds with the requested error code."""
    response = await async_grpcbin_client.specific_error(
        code=code_number(grpc.StatusCode.RESOURCE_EXHAUSTED),
        reason="квота исчерпана",
    )

    assert_that(response).has_status_code(grpc.StatusCode.RESOURCE_EXHAUSTED)


async def test_returns_error_reason_in_details(async_grpcbin_client: AsyncGRPCbinServiceClient) -> None:
    """The service error text appears in response details."""
    reason = "рейс отменен"

    response = await async_grpcbin_client.specific_error(code=code_number(grpc.StatusCode.ABORTED), reason=reason)

    assert_that(response).has_details(reason)


async def test_collects_all_messages_of_server_stream(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A collected response stream contains all messages sent by the service."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    response = await stream.collect()

    assert_that(response.message()).is_length(STREAM_MESSAGES_COUNT)


async def test_returns_ok_status_after_collecting_stream(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A collected response stream finishes with status OK."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    response = await stream.collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_reads_server_stream_lazily(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A response stream is read one message at a time."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)

    async with stream:
        first = await anext(aiter(stream))

    assert_that(first).is_instance_of(grpcbin_pb2.DummyMessage)


async def test_rejects_second_reading_of_stream(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Reading the stream again raises an error."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    await stream.collect()

    with pytest.raises(StreamConsumedError):
        await stream.collect()


async def test_sends_metadata(async_grpcbin_client: AsyncGRPCbinServiceClient) -> None:
    """Request metadata reaches the service."""
    response = await async_grpcbin_client.get_headers({"x-shipment": "SH-77"})

    assert_that(response).received_metadata("x-shipment", "SH-77")


async def test_sends_bearer_token(service_addr: str) -> None:
    """The access token is sent in the authorization header."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(FakeAsyncAuth(prefix="delivery")),
    ) as client:
        response = await client.get_headers()

    assert_that(response).received_metadata("authorization", "Bearer delivery-1")


async def test_refreshes_token_after_unauthenticated(service_addr: str) -> None:
    """A new token is issued after an UNAUTHENTICATED response."""
    auth = FakeAsyncAuth()

    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(auth),
    ) as client:
        await client.specific_error(code=code_number(grpc.StatusCode.UNAUTHENTICATED), reason="токен просрочен")

    assert_that(auth.issued).is_length(2)


async def test_rejects_sync_auth_in_async_client(service_addr: str) -> None:
    """The asynchronous client rejects synchronous authentication implementations."""
    with pytest.raises(TypeError):
        AsyncGRPCbinServiceClient.from_addr(
            service_addr,
            options.with_insecure_channel(),
            options.with_auth(FakeAuth()),
        )


async def test_adds_generated_request_id(service_addr: str) -> None:
    """The client adds a generated identifier to requests."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_autogenerated_request_id(),
    ) as client:
        response = await client.get_headers()

    assert_that(response).received_metadata_matching(
        "x-request-id",
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    )


async def test_logs_sent_request(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """The sent request is logged."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="асинхронная накладная"))

    assert_that(log_stream).logged("GRPC request sent")


async def test_logs_received_response(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """The received response is logged."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="асинхронный акт"))

    assert_that(log_stream).logged("GRPC response received")


async def test_completes_server_stream_with_logging_interceptor(
    service_addr: str,
    logger: logging.Logger,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Response streaming works with client logging enabled."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        stream = await client.send_server_stream(dummy_message)
        response = await stream.collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_repeats_call_after_unauthenticated() -> None:
    """The request is retried after an UNAUTHENTICATED response."""
    prefix = uuid4().hex
    continuation = FakeAsyncContinuation(accepted_token=f"{prefix}-2")
    interceptor = AsyncAuthInterceptor(FakeAsyncAuth(prefix=prefix))

    await interceptor.intercept_unary_unary(continuation, fake_aio_call_details(), object())

    assert_that(continuation.calls).is_length(2)


async def test_sends_refreshed_token_in_repeated_call() -> None:
    """The retry uses the new token."""
    prefix = uuid4().hex
    continuation = FakeAsyncContinuation(accepted_token=f"{prefix}-2")
    interceptor = AsyncAuthInterceptor(FakeAsyncAuth(prefix=prefix))

    await interceptor.intercept_unary_unary(continuation, fake_aio_call_details(), object())

    assert_that(continuation.sent_token(1)).is_equal_to(f"{prefix}-2")


async def test_passes_rejected_token_to_refresh() -> None:
    """The token provider is told exactly which token the service rejected."""
    prefix = uuid4().hex
    auth = FakeAsyncAuth(prefix=prefix)
    interceptor = AsyncAuthInterceptor(auth)

    await interceptor.intercept_unary_unary(
        FakeAsyncContinuation(accepted_token=f"{prefix}-2"),
        fake_aio_call_details(),
        object(),
    )

    assert_that(auth.rejected).is_equal_to([f"{prefix}-1"])


async def test_gives_up_after_single_repeat() -> None:
    """If the new token is also rejected, there is no third attempt."""
    continuation = FakeAsyncContinuation(accepted_token=None)
    interceptor = AsyncAuthInterceptor(FakeAsyncAuth())

    await interceptor.intercept_unary_unary(continuation, fake_aio_call_details(), object())

    assert_that(continuation.calls).is_length(2)


async def test_keeps_user_defined_authorization(service_addr: str) -> None:
    """The caller's custom authorization header is preserved."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_auth(FakeAsyncAuth()),
    ) as client:
        response = await client.get_headers({"authorization": "Bearer async-own-token"})

    assert_that(response).received_metadata("authorization", "Bearer async-own-token")


async def test_rejects_interceptors_for_external_channel(service_addr: str) -> None:
    """Interceptors cannot be added to an existing asynchronous channel."""
    channel = grpc.aio.insecure_channel(service_addr)

    with pytest.raises(ValueError, match="готовому асинхронному каналу"):
        AsyncGRPCbinServiceClient.from_channel(channel, options.with_autogenerated_request_id())

    await channel.close(None)


async def test_sends_request_through_external_channel(service_addr: str) -> None:
    """The client works over an existing asynchronous channel."""
    channel = grpc.aio.insecure_channel(service_addr)
    client = AsyncGRPCbinServiceClient.from_channel(channel)

    response = await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="внешний канал"))
    await channel.close(None)

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_keeps_external_channel_open_after_close(service_addr: str) -> None:
    """An externally supplied channel keeps working after the client closes."""
    channel = grpc.aio.insecure_channel(service_addr)
    client = AsyncGRPCbinServiceClient.from_channel(channel)
    await client.close()

    response = await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="канал жив"))
    await channel.close(None)

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_returns_ok_status_for_client_stream(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """A request stream finishes with status OK."""
    response = await async_grpcbin_client.send_client_stream(dummy_messages)

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_collects_all_messages_of_bidirectional_stream(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """A bidirectional stream returns as many messages as were sent."""
    stream = await async_grpcbin_client.send_bidirectional_stream(dummy_messages)
    response = await stream.collect()

    assert_that(response.message()).is_length(STREAM_MESSAGES_COUNT)


async def test_reports_deadline_exceeded_for_interrupted_stream(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A timed-out stream becomes a response with an error status."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message, CallOptions(timeout=0.05))
    response = await stream.collect()

    assert_that(response).has_status_code(grpc.StatusCode.DEADLINE_EXCEEDED)


async def test_stops_collecting_stream_at_limit(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Stream collection stops at the specified limit."""
    limit = 2

    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    response = await stream.collect(limit=limit)

    assert_that(response.message()).is_length(limit)


async def test_reports_cancelled_status_after_cancel(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A cancelled stream reports status CANCELLED."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    await anext(aiter(stream))
    stream.cancel()

    assert_that(await stream.status_code()).is_equal_to(grpc.StatusCode.CANCELLED)


async def test_logs_finished_stream_after_cancel(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Stream cancellation still produces a completion log record."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        stream = await client.send_server_stream(dummy_message)
        await anext(aiter(stream))
        stream.cancel()

    assert_that(log_stream).logged("GRPC error occurred")


async def test_logs_finished_server_stream(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Response stream completion is logged by the asynchronous client."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        stream = await client.send_server_stream(dummy_message)
        await stream.collect()

    assert_that(log_stream).logged("GRPC stream finished")


async def test_logs_number_of_streamed_messages(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """The asynchronous client logs the number of received stream messages."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        stream = await client.send_server_stream(dummy_message)
        await stream.collect()

    assert_that(log_stream).logged(f"Messages: {STREAM_MESSAGES_COUNT}")


def test_splits_multi_interface_interceptor() -> None:
    """An interceptor supporting all call types is split into separate objects.

    grpc.aio places an interceptor in only one chain, so a multi-interceptor
    supplied as a single object would serve only one call type.
    """
    interceptor = AsyncAutogenerateRequestIdInterceptor()

    assert_that(split_async_interceptor(interceptor)).is_length(4)


def test_keeps_single_interface_interceptor_as_is() -> None:
    """An interceptor with a single interface does not need splitting."""

    class SingleInterface(AsyncUnaryUnaryBase):
        @override
        async def intercept_unary_unary(
            self, continuation: AsyncUnaryContinuation, client_call_details: grpc.aio.ClientCallDetails, request: object
        ) -> object:
            return await continue_async(continuation, client_call_details, request)

    interceptor = SingleInterface()

    assert_that(split_async_interceptor(interceptor)).is_equal_to([interceptor])


async def test_reads_nothing_with_zero_limit(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A zero limit prevents any stream reads."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    response = await stream.collect(limit=0)

    assert_that(response.message()).is_empty()


async def test_makes_no_reads_with_zero_limit() -> None:
    """A zero limit prevents requesting messages from the call.

    Use a fake call: an empty list cannot distinguish no reads
    from reading and discarding messages.
    """
    call = FakeAsyncStreamCall(messages_count=3)
    stream: AsyncGRPCStreamResponse[object] = AsyncGRPCStreamResponse(cast("grpc.aio.Call", call))

    await stream.collect(limit=0)

    assert_that(call.reads).is_equal_to(0)


async def test_rejects_negative_limit(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """A negative message count limit is rejected."""
    stream = await async_grpcbin_client.send_server_stream(dummy_message)

    with pytest.raises(ValueError, match="отрицательным"):
        await stream.collect(limit=-1)


async def test_propagates_external_cancellation_of_collect(
    async_grpcbin_client: AsyncGRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Cancellation of the stream reader task reaches the caller.

    Swallowing it would break asyncio.timeout and graceful application shutdown.
    """
    stream = await async_grpcbin_client.send_server_stream(dummy_message)
    task = asyncio.create_task(stream.collect())
    await asyncio.sleep(0.2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_writes_final_log_before_close_returns(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """An unfinished stream is logged before close() returns.

    The stream is interrupted when the channel closes, so its logging task appears
    after the first drain.
    """
    client = AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    )
    stream = await client.send_server_stream(dummy_message)
    await anext(aiter(stream))

    await client.close()

    assert_that(log_stream).logged("GRPC error occurred")


async def test_leaves_no_pending_log_tasks_after_close(
    service_addr: str,
    logger: logging.Logger,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Closing the client leaves no pending logging tasks."""
    interceptor = AsyncLoggingInterceptor(logger=logger)
    client = AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_interceptor(interceptor),
    )
    stream = await client.send_server_stream(dummy_message)
    await anext(aiter(stream))

    await client.close()

    assert_that(interceptor.pending_log_tasks).is_empty()


async def test_applies_all_interceptor_types_of_multi_interceptor(service_addr: str) -> None:
    """An interceptor supporting all call types runs for each of them.

    Use real calls: grpc.aio assigns interceptors to chains itself,
    and errors here are invisible from types or adapter counts.
    """
    recorder = _RecordingInterceptor()

    def configure(client: BaseGRPCClient[object]) -> None:
        client.add_interceptor(recorder)

    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        configure,
    ) as client:
        await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="unary"))
        stream = await client.send_server_stream(grpcbin_pb2.DummyMessage(f_string="server"))
        await stream.collect()
        await client.send_client_stream(iter([grpcbin_pb2.DummyMessage(f_string="client")]))
        bidi = await client.send_bidirectional_stream(iter([grpcbin_pb2.DummyMessage(f_string="bidi")]))
        await bidi.collect()

    assert_that(recorder.seen).is_equal_to(["unary_unary", "unary_stream", "stream_unary", "stream_stream"])


class _RecordingInterceptor(AsyncMetadataInterceptor):
    def __init__(self) -> None:
        """Create a call type recorder."""
        self.seen: list[str] = []

    @override
    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        return ()

    @override
    async def intercept_unary_unary(
        self, continuation: AsyncUnaryContinuation, client_call_details: grpc.aio.ClientCallDetails, request: object
    ) -> object:
        self.seen.append("unary_unary")
        return await super().intercept_unary_unary(continuation, client_call_details, request)

    @override
    async def intercept_unary_stream(
        self,
        continuation: AsyncUnaryStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        self.seen.append("unary_stream")
        return await super().intercept_unary_stream(continuation, client_call_details, request)

    @override
    async def intercept_stream_unary(
        self,
        continuation: AsyncStreamUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        self.seen.append("stream_unary")
        return await super().intercept_stream_unary(continuation, client_call_details, request_iterator)

    @override
    async def intercept_stream_stream(
        self,
        continuation: AsyncStreamStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.StreamStreamCall[object, object]:
        self.seen.append("stream_stream")
        return await super().intercept_stream_stream(continuation, client_call_details, request_iterator)


async def test_keeps_messages_received_before_error() -> None:
    """Messages received before a server error remain in the collected response."""
    received = object()
    call = FakeFailingAsyncStreamCall([received], _aio_error())
    stream: AsyncGRPCStreamResponse[object] = AsyncGRPCStreamResponse(cast("grpc.aio.Call", call))

    response = await stream.collect()

    assert_that(response.message()).is_equal_to([received])


async def test_reports_error_status_for_interrupted_stream() -> None:
    """An interrupted stream reports the server error code."""
    call = FakeFailingAsyncStreamCall([object()], _aio_error())
    stream: AsyncGRPCStreamResponse[object] = AsyncGRPCStreamResponse(cast("grpc.aio.Call", call))

    response = await stream.collect()

    assert_that(response).has_status_code(grpc.StatusCode.RESOURCE_EXHAUSTED)


async def test_keeps_original_error_of_interrupted_stream() -> None:
    """An interrupted stream response retains the original gRPC error."""
    error = _aio_error()
    call = FakeFailingAsyncStreamCall([object()], error)
    stream: AsyncGRPCStreamResponse[object] = AsyncGRPCStreamResponse(cast("grpc.aio.Call", call))

    response = await stream.collect()

    assert_that(response.error).is_same_as(error)


def _aio_error() -> grpc.aio.AioRpcError:
    """Build an asynchronous call error for a fake stream."""
    return grpc.aio.AioRpcError(
        code=grpc.StatusCode.RESOURCE_EXHAUSTED,
        initial_metadata=grpc.aio.Metadata(),
        trailing_metadata=grpc.aio.Metadata(),
        details="квота исчерпана",
        debug_error_string="",
    )


async def test_counts_message_delivered_together_with_completion(
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """A message is counted even if the call finishes while yielding it."""
    call = FakeAsyncCallbackStreamCall(messages_count=1)
    interceptor = AsyncLoggingInterceptor(logger=logger)

    async def continuation(_details: object, _request: object) -> object:
        return call

    wrapped = await interceptor.intercept_unary_stream(continuation, fake_aio_call_details(), object())
    async for _ in wrapped:
        pass
    await interceptor.drain()

    assert_that(log_stream).logged("Messages: 1")
