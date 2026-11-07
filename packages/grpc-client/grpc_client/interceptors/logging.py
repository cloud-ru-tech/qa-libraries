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

# Имя намеренно отличается от параметра `logger`, чтобы одно не заслоняло другое внутри методов.
_logger = logging.getLogger(__name__)


class _Cancelable(Protocol):
    def cancel(self) -> bool: ...


class InterceptorLogOptions(LoggerOptions, total=False):
    """Настройки логирования интерцептора."""

    sink: LogSink | None


class _LoggingBase:
    """Общие настройки логирующих интерцепторов.

    Класс отвечает за то, *что* произошло с вызовом: собирает записи и выбирает уровень.
    Куда и в каком виде запись попадет, решает приемник.
    """

    def __init__(self, logger: logging.Logger | None = None, **settings: Unpack[InterceptorLogOptions]) -> None:
        """Создать интерцептор с логгером или приемником записей.

        :param logger: стандартный логгер.
        :param settings: уровни, оформление и альтернативный приемник записей.
        :raises TypeError: если задано неверное сочетание логгера и приемника.
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
        """Проверить, что логирование выключено для обоих уровней.

        В этом случае интерцептору нечего делать: он не должен ни генерировать идентификатор,
        ни оборачивать поток ради подсчета сообщений.
        """
        return not self._is_enabled_for(self._log_level) and not self._is_enabled_for(self._err_log_level)

    def _is_enabled_for(self, level: int) -> bool:
        """Спросить приемник, дойдет ли запись указанного уровня до вывода.

        Отказ приемника трактуется как выключенный уровень: запись пропускается, вызов идет дальше.
        """
        try:
            return self._sink.is_enabled_for(level)
        except Exception as error:  # noqa: BLE001 — сбой приемника не должен ломать вызов
            _report_sink_failure(error)
            return False

    def _write_request(self, level: int, record: RequestRecord) -> None:
        """Отдать приемнику запись о запросе, погасив его возможный сбой."""
        try:
            self._sink.write_request(level, record)
        except Exception as error:  # noqa: BLE001 — сбой приемника не должен ломать вызов
            _report_sink_failure(error)

    def _write_response(self, level: int, record: ResponseRecord) -> None:
        """Отдать приемнику запись о завершившемся вызове, погасив его возможный сбой."""
        try:
            self._sink.write_response(level, record)
        except Exception as error:  # noqa: BLE001 — сбой приемника не должен ломать вызов
            _report_sink_failure(error)

    def _outcome_level(self, code: grpc.StatusCode) -> int:
        """Выбрать уровень записи по исходу вызова."""
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
    """Интерцептор, логирующий gRPC-запросы и ответы.

    Поддерживает все четыре типа вызовов. Тело потока запросов и потока ответов в лог не попадает:
    вычитывание потока ради лога изменило бы поведение вызова. Для потока ответов логируется
    итоговый статус и количество полученных сообщений.
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
    """Асинхронный интерцептор, логирующий gRPC-запросы и ответы."""

    def __init__(self, logger: logging.Logger | None = None, **settings: Unpack[InterceptorLogOptions]) -> None:
        """Создать экземпляр с переданными настройками."""
        super().__init__(logger, **settings)

        # Реестр создается здесь, а не лениво: объект может попасть сразу в несколько потоков,
        # и ленивая инициализация выдала бы им разные блокировки.
        self._log_tasks: MutableMapping[asyncio.AbstractEventLoop, set[asyncio.Task[None]]] = (
            weakref.WeakKeyDictionary()
        )
        self._registry_lock = threading.Lock()

    @property
    def pending_log_tasks(self) -> set[asyncio.Task[None]]:
        """Незавершенные задачи записи финального лога текущего событийного цикла."""
        return self._tasks_of_current_loop()

    def _tasks_of_current_loop(self) -> set[asyncio.Task[None]]:
        """Получить набор задач, принадлежащих текущему циклу событий.

        Один интерцептор может обслуживать клиентов в разных циклах, поэтому наборы
        разделены: иначе набор менялся бы из чужого потока прямо во время обхода.
        Ссылки на циклы слабые — закрытый цикл не удерживается реестром.
        """
        loop = asyncio.get_running_loop()

        with self._registry_lock:
            return self._log_tasks.setdefault(loop, set())

    async def drain(self) -> None:
        """Дождаться записи всех отложенных логов.

        Финальный лог потока пишется отдельной задачей, поэтому при закрытии клиента
        ее нужно дождаться — иначе последняя запись потеряется.
        """
        while True:
            own = tuple(self._tasks_of_current_loop())
            if not own:
                return

            await asyncio.gather(*own, return_exceptions=True)
            # Задача лога могла появиться, пока мы ждали предыдущие: даем циклу шанс их создать.
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
        """Записать исход асинхронного вызова.

        :param trace_id: идентификатор, связывающий запрос с ответом
        :param call_details: параметры вызова
        :param call: объект завершившегося вызова
        :param messages_count: количество полученных сообщений, `None` для унарного вызова
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
    """Обертка над потоковым вызовом, считающая полученные сообщения.

    Все остальные обращения делегируются исходному вызову, поэтому обертка остается полноценным `grpc.Call`.
    """

    def __init__(self, call: object, on_finish: Callable[[int], None]) -> None:
        """Создать экземпляр с переданными настройками."""
        self._call = call
        self._on_finish = on_finish
        self._count = 0
        self._finished = False
        self._reading = False
        self._finish_requested = False
        # Callback завершения grpcio вызывает из служебного потока канала, поэтому счетчик
        # и признак завершения нужно защищать: иначе возможны двойной лог и потерянные сообщения.
        self._lock = threading.Lock()

        # Поток могут не дочитать: он завершится сам по ошибке, deadline или закрытию канала.
        # Тогда единственный шанс записать финальный лог — callback самого вызова.
        add_done_callback = cast(
            "Callable[[Callable[[object], None]], None] | None", getattr(call, "add_done_callback", None)
        )
        if callable(add_done_callback):
            add_done_callback(lambda _: self._request_finish())

    def __iter__(self) -> Iterator[object]:
        """Получить итератор значений."""
        return self

    def __next__(self) -> object:
        """Получить следующее сообщение потока."""
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

        # Вызов мог завершиться, пока мы читали сообщение: тогда финальный лог откладывался
        # до этого момента, чтобы в него попало уже прочитанное сообщение.
        if finish_now:
            self._finish()

        return message

    def _request_finish(self) -> None:
        """Записать финальный лог или отложить его до конца текущего чтения."""
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
    """Обертка над асинхронным потоковым вызовом, считающая полученные сообщения.

    Финальный лог вешается на сам вызов через `add_done_callback`: grpc.aio оборачивает
    результат интерцептора в собственный объект, поэтому отмену обертка не увидит.

    ⚠️ Считаются только сообщения, полученные асинхронной итерацией. Чтение методом `read()`
    grpc.aio выполняет мимо объекта интерцептора, поэтому такие сообщения в счетчик не попадают —
    в логе завершения потока их не будет.
    """

    def __init__(self, call: object) -> None:
        """Создать экземпляр с переданными настройками."""
        self._call = call
        self._iterator: AsyncIterator[object] | None = None
        self.count = 0
        self._reading = False
        self._pending_finish: Callable[[], None] | None = None

    def __aiter__(self) -> AsyncIterator[object]:
        """Получить асинхронный итератор сообщений."""
        return self

    async def __anext__(self) -> object:
        # Объект вызова grpc.aio отдает сообщения через отдельный итератор, а сам методом
        # __anext__ не обладает, поэтому итератор берется у него при первом чтении.
        """Получить следующее сообщение потока."""
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

        # Вызов мог завершиться, пока мы ждали сообщение: финальный лог отложен до этого
        # момента, чтобы в него попало уже полученное сообщение.
        self._run_pending_finish()
        return message

    def defer_if_reading(self, schedule_log: Callable[[], None]) -> bool:
        """Отложить запись финального лога, если прямо сейчас читается сообщение.

        :param schedule_log: функция, запускающая запись лога
        :return: True, если запись отложена до конца чтения
        """
        if not self._reading:
            return False

        self._pending_finish = schedule_log
        return True

    def _run_pending_finish(self) -> None:
        """Запустить отложенную запись лога, если она была запрошена во время чтения."""
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
    """Запланировать запись лога на момент завершения асинхронного вызова.

    Задача сохраняется в переданном наборе: иначе сборщик мусора может убрать ее до записи,
    а исключение внутри останется незамеченным.

    :param call: объект асинхронного вызова
    :param build_log: функция, создающая корутину записи лога
    :param tasks: набор незавершенных задач логирования
    :param counting: обертка потока, у которой уточняется, идет ли сейчас чтение
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

        # Пока обертка читает сообщение, счетчик еще не обновлен: тогда запись откладывается
        # и запускается самой оберткой сразу после инкремента.
        if counting is not None and counting.defer_if_reading(schedule_log):
            return

        schedule_log()

    add_done_callback(_on_done)


def _forget_task(tasks: set[asyncio.Task[None]]) -> Callable[[asyncio.Task[None]], None]:
    """Создать обработчик завершения задачи логирования."""

    def _on_finished(task: asyncio.Task[None]) -> None:
        tasks.discard(task)
        if task.cancelled():
            return

        # Исключение нужно забрать, иначе интерпретатор напишет о необработанной ошибке задачи.
        # Но и молчать нельзя: иначе пропажа финального лога останется незамеченной.
        error = task.exception()
        if error is not None:
            _report_log_failure(error)

    return _on_finished


def _report_sink_failure(error: BaseException) -> None:
    """Сообщить о сбое приемника записей.

    Приемник может быть чужим кодом, а лог запроса собирается до отправки: падение приемника
    сорвало бы сам вызов. Поэтому запись теряется, но запрос уходит, а ответ доходит до вызывающего.

    :param error: исключение, выброшенное приемником
    """
    _logger.warning("Приемник лога gRPC не смог записать вызов", exc_info=error)


def _report_log_failure(error: BaseException) -> None:
    """Сообщить о сбое записи отложенного лога через обработчик событийного цикла."""
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
    """Достать ответное сообщение из завершенного вызова."""
    result = cast("Callable[[], object] | None", getattr(outcome, "result", None))
    if not callable(result):
        return None

    try:
        message = result()
    except Exception:  # noqa: BLE001 — недоступный результат не должен ломать логирование
        return None

    return cast("Message", message) if isinstance(message, cast("type[object]", Message)) else None


def _details(outcome: object) -> str:
    details = cast("Callable[[], object] | None", getattr(outcome, "details", None))
    if not callable(details):
        return ""

    try:
        return str(details() or "")
    except Exception:  # noqa: BLE001 — недоступные детали не должны ломать логирование
        return ""


def _trailing_metadata(outcome: object) -> MetadataType | None:
    metadata = cast("Callable[[], MetadataType | None] | None", getattr(outcome, "trailing_metadata", None))
    if not callable(metadata):
        return None

    try:
        return metadata()
    except Exception:  # noqa: BLE001 — недоступные метаданные не должны ломать логирование
        return None


async def _async_code(call: object) -> grpc.StatusCode:
    try:
        return await cast("grpc.aio.Call", call).code()
    except grpc.aio.AioRpcError as error:
        return error.code()
    # CancelledError наследуется от BaseException, поэтому его нужно ловить отдельно:
    # именно он приходит, когда статус запрашивают у только что отмененного вызова.
    except asyncio.CancelledError:
        return grpc.StatusCode.CANCELLED
    except Exception:  # noqa: BLE001 — недоступный статус не должен ломать логирование
        return grpc.StatusCode.UNKNOWN


async def _async_details(call: object) -> str:
    try:
        return str(await cast("grpc.aio.Call", call).details() or "")
    except grpc.aio.AioRpcError as error:
        return error.details() or ""
    except asyncio.CancelledError:
        return ""
    except Exception:  # noqa: BLE001 — недоступные детали не должны ломать логирование
        return ""


async def _async_trailing_metadata(call: object) -> MetadataType | None:
    try:
        return cast("MetadataType | None", await cast("grpc.aio.Call", call).trailing_metadata())
    except asyncio.CancelledError:
        return None
    except Exception:  # noqa: BLE001 — недоступные метаданные не должны ломать логирование
        return None


async def _async_result(call: object) -> Message | None:
    try:
        message = await cast("Awaitable[object]", call)
    except Exception:  # noqa: BLE001 — недоступный результат не должен ломать логирование
        return None

    return cast("Message", message) if isinstance(message, cast("type[object]", Message)) else None
