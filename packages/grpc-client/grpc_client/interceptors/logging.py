from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from typing import TYPE_CHECKING, Protocol, Unpack, cast, override
from uuid import uuid4

import grpc
from google.protobuf.message import Message

from grpc_client.logsink import LogSink, RequestRecord, ResponseRecord, TextLogSink, resolve_log_levels
from grpc_client.utils.logutils import LogFormat, LoggerOptions

from .base import (
    AsyncStreamStreamBase,
    AsyncStreamStreamContinuation,
    AsyncStreamUnaryBase,
    AsyncStreamUnaryContinuation,
    AsyncUnaryContinuation,
    AsyncUnaryStreamBase,
    AsyncUnaryStreamContinuation,
    AsyncUnaryUnaryBase,
    ContinuationType,
    StreamContinuation,
    SyncStreamStreamBase,
    SyncStreamUnaryBase,
    SyncUnaryStreamBase,
    SyncUnaryUnaryBase,
    call_detail,
    continue_async,
    method_name,
    outcome_code,
)

if TYPE_CHECKING:
    from collections.abc import (
        AsyncIterable,
        AsyncIterator,
        Awaitable,
        Callable,
        Coroutine,
        Iterable,
        Iterator,
        MutableMapping,
    )

    from grpc_client.types import MetadataType

# The name intentionally differs from `logger` to avoid shadowing inside methods.
_logger = logging.getLogger(__name__)


class _Cancelable(Protocol):
    def cancel(self) -> bool: ...


class InterceptorLogOptions(LoggerOptions, total=False):
    """Interceptor logging settings."""

    sink: LogSink | None


class _LoggingBase:
    """Shared logging interceptor settings.

    The class describes *what* happened to the call: it builds records and selects levels.
    The sink decides where and how the record is written.
    """

    def __init__(self, logger: logging.Logger | None = None, **settings: Unpack[InterceptorLogOptions]) -> None:
        """Create an interceptor with a logger or record sink.

        :param logger: standard logger.
        :param settings: levels, formatting, and alternative record sink.
        :raises TypeError: if the logger and sink combination is invalid.
        """
        sink = settings.get("sink")
        sanitize_keys = settings.get("sanitize_keys")
        json_indent = settings.get("json_indent")
        use_line_breaks = settings.get("use_line_breaks")
        payload_maxlength = settings.get("payload_maxlength")
        use_default_sanitize_keys = settings.get("use_default_sanitize_keys", True)
        log_level = settings.get("log_level")
        err_log_level = settings.get("err_log_level")
        if (logger is None) == (sink is None):
            message = "Логирующему интерцептору нужен ровно один из параметров: logger либо sink"
            raise TypeError(message)
        self._sink: LogSink = (
            sink
            if sink is not None
            else TextLogSink(
                cast("logging.Logger", logger),
                LogFormat.from_config(
                    sanitize_keys=sanitize_keys,
                    json_indent=json_indent,
                    use_line_breaks=use_line_breaks,
                    payload_maxlength=payload_maxlength,
                    use_default_sanitize_keys=use_default_sanitize_keys,
                ),
            )
        )
        self._log_level, self._err_log_level = resolve_log_levels(log_level, err_log_level)

    def _is_disabled(self) -> bool:
        """Check whether logging is disabled at both levels.

        In this case the interceptor has nothing to do: it must neither generate an identifier
        nor wrap the stream to count messages.
        """
        return not self._is_enabled_for(self._log_level) and not self._is_enabled_for(self._err_log_level)

    def _is_enabled_for(self, level: int) -> bool:
        """Ask the sink whether records at the specified level reach the output.

        A sink failure is treated as a disabled level: skip the record and continue the call.
        """
        try:
            return self._sink.is_enabled_for(level)
        except Exception as error:  # noqa: BLE001 - a sink failure must not break the call
            _report_sink_failure(error)
            return False

    def _write_request(self, level: int, record: RequestRecord) -> None:
        """Pass a request record to the sink, suppressing any sink failure."""
        try:
            self._sink.write_request(level, record)
        except Exception as error:  # noqa: BLE001 - a sink failure must not break the call
            _report_sink_failure(error)

    def _write_response(self, level: int, record: ResponseRecord) -> None:
        """Pass a completed call record to the sink, suppressing any sink failure."""
        try:
            self._sink.write_response(level, record)
        except Exception as error:  # noqa: BLE001 - a sink failure must not break the call
            _report_sink_failure(error)

    def _outcome_level(self, code: grpc.StatusCode) -> int:
        """Choose the log level based on the call outcome."""
        return self._log_level if code is grpc.StatusCode.OK else self._err_log_level

    def _log_request(self, trace_id: str, call_details: object, message: Message | None) -> None:
        if not self._is_enabled_for(self._log_level):
            return

        self._write_request(
            self._log_level,
            RequestRecord(
                trace_id=trace_id,
                method=method_name(call_details),
                message=message,
                metadata=call_detail(call_details, "metadata", None),
            ),
        )

    def _log_unary_outcome(self, trace_id: str, call_details: object, outcome: object) -> None:
        code = outcome_code(outcome) or grpc.StatusCode.UNKNOWN
        level = self._outcome_level(code)
        if not self._is_enabled_for(level):
            return

        succeeded = code is grpc.StatusCode.OK
        self._write_response(
            level,
            ResponseRecord(
                trace_id=trace_id,
                method=method_name(call_details),
                status_code=code,
                message=_result_message(outcome) if succeeded else None,
                details="" if succeeded else _details(outcome),
                metadata=_trailing_metadata(outcome),
                messages_count=None,
            ),
        )

    def _log_stream_finish(self, trace_id: str, call_details: object, call: object, messages_count: int) -> None:
        code = outcome_code(call) or grpc.StatusCode.UNKNOWN
        level = self._outcome_level(code)
        if not self._is_enabled_for(level):
            return

        succeeded = code is grpc.StatusCode.OK
        self._write_response(
            level,
            ResponseRecord(
                trace_id=trace_id,
                method=method_name(call_details),
                status_code=code,
                message=None,
                details="" if succeeded else _details(call),
                metadata=_trailing_metadata(call),
                messages_count=messages_count,
            ),
        )


class LoggingInterceptor(
    _LoggingBase,
    SyncUnaryUnaryBase,
    SyncUnaryStreamBase,
    SyncStreamUnaryBase,
    SyncStreamStreamBase,
):
    """Interceptor that logs gRPC requests and responses.

    Supports all four call types. Request and response stream bodies are not logged:
    reading the stream for logging would change call behavior. For response streams, log
    the final status and number of received messages.
    """

    @override
    def intercept_unary_unary(
        self, continuation: ContinuationType, client_call_details: grpc.ClientCallDetails, request: object
    ) -> grpc.CallFuture[object]:
        if self._is_disabled():
            return cast("grpc.CallFuture[object]", continuation(client_call_details, request))

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, cast("Message", request))

        outcome = continuation(client_call_details, request)
        self._log_unary_outcome(trace_id, client_call_details, outcome)
        return cast("grpc.CallFuture[object]", outcome)

    @override
    def intercept_stream_unary(
        self,
        continuation: ContinuationType,
        client_call_details: grpc.ClientCallDetails,
        request_iterator: Iterator[object],
    ) -> grpc.CallFuture[object]:
        if self._is_disabled():
            return cast("grpc.CallFuture[object]", continuation(client_call_details, request_iterator))

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, None)

        outcome = continuation(client_call_details, request_iterator)
        self._log_unary_outcome(trace_id, client_call_details, outcome)
        return cast("grpc.CallFuture[object]", outcome)

    @override
    def intercept_unary_stream(
        self, continuation: StreamContinuation, client_call_details: grpc.ClientCallDetails, request: object
    ) -> grpc.CallIterator[object]:
        if self._is_disabled():
            return cast("grpc.CallIterator[object]", continuation(client_call_details, request))

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, cast("Message", request))

        call = continuation(client_call_details, request)
        return cast(
            "grpc.CallIterator[object]",
            _CountingCall(call, lambda count: self._log_stream_finish(trace_id, client_call_details, call, count)),
        )

    @override
    def intercept_stream_stream(
        self,
        continuation: StreamContinuation,
        client_call_details: grpc.ClientCallDetails,
        request_iterator: Iterator[object],
    ) -> grpc.CallIterator[object]:
        if self._is_disabled():
            return cast("grpc.CallIterator[object]", continuation(client_call_details, request_iterator))

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, None)

        call = continuation(client_call_details, request_iterator)
        return cast(
            "grpc.CallIterator[object]",
            _CountingCall(call, lambda count: self._log_stream_finish(trace_id, client_call_details, call, count)),
        )


class AsyncLoggingInterceptor(
    _LoggingBase,
    AsyncUnaryUnaryBase,
    AsyncUnaryStreamBase,
    AsyncStreamUnaryBase,
    AsyncStreamStreamBase,
):
    """Asynchronous interceptor that logs gRPC requests and responses."""

    def __init__(self, logger: logging.Logger | None = None, **settings: Unpack[InterceptorLogOptions]) -> None:
        """Create an instance with the supplied settings."""
        super().__init__(logger, **settings)

        # Create the registry eagerly: the object may immediately be shared across threads,
        # and lazy initialization would give them different locks.
        self._log_tasks: MutableMapping[asyncio.AbstractEventLoop, set[asyncio.Task[None]]] = (
            weakref.WeakKeyDictionary()
        )
        self._registry_lock = threading.Lock()

    @property
    def pending_log_tasks(self) -> set[asyncio.Task[None]]:
        """Pending final log tasks for the current event loop."""
        return self._tasks_of_current_loop()

    def _tasks_of_current_loop(self) -> set[asyncio.Task[None]]:
        """Get the task set belonging to the current event loop.

        One interceptor can serve clients in different loops, so the sets are
        separate, otherwise another thread could modify the set during iteration.
        Event loop references are weak, so the registry does not retain closed loops.
        """
        loop = asyncio.get_running_loop()

        with self._registry_lock:
            return self._log_tasks.setdefault(loop, set())

    async def drain(self) -> None:
        """Wait for all deferred logs to be written.

        The final stream log runs in a separate task, so when closing the client
        await it or the final record will be lost.
        """
        while True:
            own = tuple(self._tasks_of_current_loop())
            if not own:
                return

            await asyncio.gather(*own, return_exceptions=True)
            # A logging task may appear while awaiting earlier tasks: let the event loop create it.
            await asyncio.sleep(0)

    @override
    async def intercept_unary_unary(
        self, continuation: AsyncUnaryContinuation, client_call_details: grpc.aio.ClientCallDetails, request: object
    ) -> object:
        if self._is_disabled():
            return await continue_async(continuation, client_call_details, request)

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, cast("Message", request))

        call: object = await continue_async(continuation, client_call_details, request)
        await self._log_async_unary(trace_id, client_call_details, call)
        return call

    @override
    async def intercept_stream_unary(
        self,
        continuation: AsyncStreamUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        if self._is_disabled():
            return await continue_async(continuation, client_call_details, request_iterator)

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, None)

        call: object = await continue_async(continuation, client_call_details, request_iterator)
        await self._log_async_unary(trace_id, client_call_details, call)
        return cast("grpc.aio.UnaryStreamCall[object, object]", call)

    @override
    async def intercept_unary_stream(
        self,
        continuation: AsyncUnaryStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> AsyncIterable[object] | grpc.aio.UnaryStreamCall[object, object]:
        if self._is_disabled():
            return await continue_async(continuation, client_call_details, request)

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, cast("Message", request))

        call: object = await continue_async(continuation, client_call_details, request)
        counting = _AsyncCountingCall(call)
        _log_when_done(
            call,
            lambda: self._log_async_stream(trace_id, client_call_details, call, counting.count),
            self.pending_log_tasks,
            counting,
        )
        return counting

    @override
    async def intercept_stream_stream(
        self,
        continuation: AsyncStreamStreamContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: AsyncIterable[object] | Iterable[object],
    ) -> AsyncIterable[object] | grpc.aio.StreamStreamCall[object, object]:
        if self._is_disabled():
            return await continue_async(continuation, client_call_details, request_iterator)

        trace_id = _trace_id()
        self._log_request(trace_id, client_call_details, None)

        call: object = await continue_async(continuation, client_call_details, request_iterator)
        counting = _AsyncCountingCall(call)
        _log_when_done(
            call,
            lambda: self._log_async_stream(trace_id, client_call_details, call, counting.count),
            self.pending_log_tasks,
            counting,
        )
        return counting

    async def _log_async_unary(self, trace_id: str, call_details: object, call: object) -> None:
        await self._log_async_outcome(trace_id, call_details, call, messages_count=None)

    async def _log_async_stream(self, trace_id: str, call_details: object, call: object, messages_count: int) -> None:
        await self._log_async_outcome(trace_id, call_details, call, messages_count=messages_count)

    async def _log_async_outcome(
        self,
        trace_id: str,
        call_details: object,
        call: object,
        messages_count: int | None,
    ) -> None:
        """Log the outcome of an asynchronous call.

        :param trace_id: identifier linking a request to its response
        :param call_details: call options
        :param call: completed call object
        :param messages_count: number of received messages, `None` for unary calls
        """
        code = await _async_code(call)
        level = self._outcome_level(code)
        if not self._is_enabled_for(level):
            return

        succeeded = code is grpc.StatusCode.OK
        streamed = messages_count is not None
        self._write_response(
            level,
            ResponseRecord(
                trace_id=trace_id,
                method=method_name(call_details),
                status_code=code,
                message=None if streamed or not succeeded else await _async_result(call),
                details="" if succeeded else await _async_details(call),
                metadata=await _async_trailing_metadata(call),
                messages_count=messages_count,
            ),
        )


class _CountingCall:
    """Wrapper around a streaming call that counts received messages.

    All other access is delegated to the original call, so the wrapper remains a complete `grpc.Call`.
    """

    def __init__(self, call: object, on_finish: Callable[[int], None]) -> None:
        """Create an instance with the supplied settings."""
        self._call = call
        self._on_finish = on_finish
        self._count = 0
        self._finished = False
        self._reading = False
        self._finish_requested = False
        # grpcio invokes the completion callback from the channel's internal thread, so the counter
        # and the completion flag need protection to avoid duplicate logs and lost messages.
        self._lock = threading.Lock()

        # A stream may remain unread and finish due to an error, deadline, or channel closure.
        # The call callback is then the only chance to write the final log.
        add_done_callback = cast(
            "Callable[[Callable[[object], None]], None] | None", getattr(call, "add_done_callback", None)
        )
        if callable(add_done_callback):
            add_done_callback(lambda _: self._request_finish())

    def __iter__(self) -> Iterator[object]:
        """Get an iterator of values."""
        return self

    def __next__(self) -> object:
        """Get the next stream message."""
        with self._lock:
            self._reading = True

        try:
            message = next(cast("Iterator[object]", self._call))
        except (StopIteration, grpc.RpcError):
            with self._lock:
                self._reading = False
            self._finish()
            raise

        with self._lock:
            self._count += 1
            self._reading = False
            finish_now = self._finish_requested

        # The call may have finished while reading a message: the final log was deferred
        # until this point to include the message already read.
        if finish_now:
            self._finish()

        return message

    def _request_finish(self) -> None:
        """Write the final log or defer it until the current read finishes."""
        with self._lock:
            if self._reading:
                self._finish_requested = True
                return

        self._finish()

    def __getattr__(self, name: str) -> object:
        return cast("object", getattr(self._call, name))

    def cancel(self) -> bool:
        cancelled = cast("_Cancelable", self._call).cancel()
        self._request_finish()
        return cancelled

    def _finish(self) -> None:
        with self._lock:
            if self._finished:
                return

            self._finished = True
            count = self._count

        self._on_finish(count)


class _AsyncCountingCall:
    """Wrapper around an asynchronous streaming call that counts received messages.

    Attach the final log to the call itself using `add_done_callback`: grpc.aio wraps
    the interceptor result in its own object, so the wrapper misses cancellation.

    Only messages received through asynchronous iteration are counted. Reading with `read()`
    grpc.aio performs outside the interceptor object, so these messages are not counted;
    they will be absent from the stream completion log.
    """

    def __init__(self, call: object) -> None:
        """Create an instance with the supplied settings."""
        self._call = call
        self._iterator: AsyncIterator[object] | None = None
        self.count = 0
        self._reading = False
        self._pending_finish: Callable[[], None] | None = None

    def __aiter__(self) -> AsyncIterator[object]:
        """Get an asynchronous message iterator."""
        return self

    async def __anext__(self) -> object:
        # The grpc.aio call object yields messages through a separate iterator and itself
        # has no __anext__, so its iterator is obtained on the first read.
        """Get the next stream message."""
        if self._iterator is None:
            self._iterator = aiter(cast("AsyncIterable[object]", self._call))

        self._reading = True
        try:
            message = await self._iterator.__anext__()
        except BaseException:
            self._reading = False
            self._run_pending_finish()
            raise

        self.count += 1
        self._reading = False

        # The call may have finished while awaiting a message: the final log is deferred until this
        # point to include the message already received.
        self._run_pending_finish()
        return message

    def defer_if_reading(self, schedule_log: Callable[[], None]) -> bool:
        """Defer the final log if a message is currently being read.

        :param schedule_log: function that starts logging
        :return: True if logging is deferred until reading finishes
        """
        if not self._reading:
            return False

        self._pending_finish = schedule_log
        return True

    def _run_pending_finish(self) -> None:
        """Run deferred logging if it was requested during reading."""
        schedule_log = self._pending_finish
        if schedule_log is None:
            return

        self._pending_finish = None
        schedule_log()

    def __getattr__(self, name: str) -> object:
        return cast("object", getattr(self._call, name))


def _log_when_done(
    call: object,
    build_log: Callable[[], Coroutine[object, object, None]],
    tasks: set[asyncio.Task[None]],
    counting: _AsyncCountingCall | None = None,
) -> None:
    """Schedule logging when an asynchronous call finishes.

    Store the task in the supplied set; otherwise garbage collection may remove it before logging,
    and an exception inside would go unnoticed.

    :param call: asynchronous call object
    :param build_log: function that creates the logging coroutine
    :param tasks: pending logging task set
    :param counting: stream wrapper queried for whether a read is in progress
    """
    add_done_callback = cast(
        "Callable[[Callable[[object], None]], None] | None", getattr(call, "add_done_callback", None)
    )
    if not callable(add_done_callback):
        return

    def _on_done(_: object) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def schedule_log() -> None:
            task = loop.create_task(build_log())
            tasks.add(task)
            task.add_done_callback(_forget_task(tasks))

        # While the wrapper reads a message, the counter is not updated yet: defer logging
        # and the wrapper runs it immediately after incrementing the counter.
        if counting is not None and counting.defer_if_reading(schedule_log):
            return

        schedule_log()

    add_done_callback(_on_done)


def _forget_task(tasks: set[asyncio.Task[None]]) -> Callable[[asyncio.Task[None]], None]:
    """Create a logging task completion handler."""

    def _on_finished(task: asyncio.Task[None]) -> None:
        tasks.discard(task)
        if task.cancelled():
            return

        # Retrieve the exception to prevent an unhandled task error from the interpreter.
        # Silently ignoring this would hide the missing final log.
        error = task.exception()
        if error is not None:
            _report_log_failure(error)

    return _on_finished


def _report_sink_failure(error: BaseException) -> None:
    """Report a record sink failure.

    The sink can be external code and request logs are built before sending: a sink failure
    would break the call. Drop the record instead, while the request is sent and the caller receives the response.

    :param error: exception raised by the sink
    """
    _logger.warning("Приемник лога gRPC не смог записать вызов", exc_info=error)


def _report_log_failure(error: BaseException) -> None:
    """Report deferred logging failures through the event loop handler."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.call_exception_handler(
        cast("dict[str, object]", {"message": "Не удалось записать финальный лог gRPC потока", "exception": error})
    )


def _trace_id() -> str:
    return str(uuid4())


def _result_message(outcome: object) -> Message | None:
    """Extract the response message from a completed call."""
    result = cast("Callable[[], object] | None", getattr(outcome, "result", None))
    if not callable(result):
        return None

    try:
        message = result()
    except Exception:  # noqa: BLE001 - an unavailable result must not break logging
        return None

    return cast("Message", message) if isinstance(message, cast("type[object]", Message)) else None


def _details(outcome: object) -> str:
    details = cast("Callable[[], object] | None", getattr(outcome, "details", None))
    if not callable(details):
        return ""

    try:
        return str(details() or "")
    except Exception:  # noqa: BLE001 - unavailable details must not break logging
        return ""


def _trailing_metadata(outcome: object) -> MetadataType | None:
    metadata = cast("Callable[[], MetadataType | None] | None", getattr(outcome, "trailing_metadata", None))
    if not callable(metadata):
        return None

    try:
        return metadata()
    except Exception:  # noqa: BLE001 - unavailable metadata must not break logging
        return None


async def _async_code(call: object) -> grpc.StatusCode:
    try:
        return await cast("grpc.aio.Call", call).code()
    except grpc.aio.AioRpcError as error:
        return error.code()
    # CancelledError inherits from BaseException and must be caught separately:
    # it is raised when querying the status of a just-cancelled call.
    except asyncio.CancelledError:
        return grpc.StatusCode.CANCELLED
    except Exception:  # noqa: BLE001 - an unavailable status must not break logging
        return grpc.StatusCode.UNKNOWN


async def _async_details(call: object) -> str:
    try:
        return str(await cast("grpc.aio.Call", call).details() or "")
    except grpc.aio.AioRpcError as error:
        return error.details() or ""
    except asyncio.CancelledError:
        return ""
    except Exception:  # noqa: BLE001 - unavailable details must not break logging
        return ""


async def _async_trailing_metadata(call: object) -> MetadataType | None:
    try:
        return cast("MetadataType | None", await cast("grpc.aio.Call", call).trailing_metadata())
    except asyncio.CancelledError:
        return None
    except Exception:  # noqa: BLE001 - unavailable metadata must not break logging
        return None


async def _async_result(call: object) -> Message | None:
    try:
        message = await cast("Awaitable[object]", call)
    except Exception:  # noqa: BLE001 - an unavailable result must not break logging
        return None

    return cast("Message", message) if isinstance(message, cast("type[object]", Message)) else None
