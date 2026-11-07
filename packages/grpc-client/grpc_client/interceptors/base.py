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
    """Вызвать продолжение grpc.aio с фактической асинхронной сигнатурой.

    :param continuation: функция продолжения grpc.aio.
    :param details: параметры вызова.
    :param request: сообщение или поток запросов.
    :return: объект выполняющегося вызова.
    """
    return await cast("Callable[[grpc.aio.ClientCallDetails, object], Awaitable[T]]", continuation)(details, request)


class ClientCallDetails(NamedTuple):
    """Параметры вызова, передаваемые по цепочке интерцепторов."""

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
    """Создать параметры вызова с дополненными метаданными.

    :param call_details: исходные параметры вызова
    :param metadata: метаданные, дописываемые в конец
    :return: новые параметры вызова
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
    """Прочитать необязательный параметр вызова grpcio."""
    return cast("object", getattr(call_details, name, default))


def method_name(call_details: object) -> str:
    """Получить полное имя вызываемого метода.

    :param call_details: параметры вызова
    :return: имя метода в виде /package.Service/Method
    """
    method = call_detail(call_details, "method", "")
    return method.decode() if isinstance(method, bytes) else str(method)


def outcome_code(outcome: object) -> grpc.StatusCode | None:
    """Определить код статуса завершенного вызова.

    Объекты вызова grpcio реализуют одновременно `grpc.Call` и `grpc.RpcError`, поэтому
    отличать успех от ошибки по типу объекта нельзя — только по коду статуса.

    :param outcome: объект, возвращенный продолжением цепочки
    :return: код статуса либо None, если объект его не сообщает
    """
    code = cast("Callable[[], object] | None", getattr(outcome, "code", None))
    if not callable(code):
        return None

    try:
        result = code()
    except Exception:  # noqa: BLE001 — недоступный статус не должен ломать вызов
        return None

    return result if isinstance(result, grpc.StatusCode) else None


class MetadataInterceptor(
    SyncUnaryUnaryBase,
    SyncUnaryStreamBase,
    SyncStreamUnaryBase,
    SyncStreamStreamBase,
    ABC,
):
    """Базовый синхронный интерцептор, дополняющий метаданные запроса.

    Наследнику достаточно реализовать `metadata_to_add()`: метаданные будут добавлены
    ко всем четырем типам вызовов.
    """

    @abstractmethod
    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Собрать метаданные, добавляемые к запросу.

        :param call_details: параметры вызова
        :return: пары ключ-значение, дописываемые к метаданным запроса
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
    """Базовый асинхронный интерцептор, дополняющий метаданные запроса."""

    @abstractmethod
    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Собрать метаданные, добавляемые к запросу.

        :param call_details: параметры вызова
        :return: пары ключ-значение, дописываемые к метаданным запроса
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
    """Создать параметры асинхронного вызова с дополненными метаданными.

    :param call_details: исходные параметры вызова
    :param metadata: метаданные, дописываемые в конец
    :return: новые параметры вызова
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
    """Разложить асинхронный интерцептор на отдельные интерфейсы grpc.aio.

    :param interceptor: исходный интерцептор.
    :return: отдельный адаптер на каждый поддерживаемый тип вызова.
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
    """Адаптер единственного интерфейса grpc.aio."""

    def __init__(self, impl: AsyncUnaryUnaryBase) -> None:
        """Сохранить реализацию интерцептора."""
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
    """Адаптер единственного интерфейса grpc.aio."""

    def __init__(self, impl: AsyncUnaryStreamBase) -> None:
        """Сохранить реализацию интерцептора."""
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
    """Адаптер единственного интерфейса grpc.aio."""

    def __init__(self, impl: AsyncStreamUnaryBase) -> None:
        """Сохранить реализацию интерцептора."""
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
    """Адаптер единственного интерфейса grpc.aio."""

    def __init__(self, impl: AsyncStreamStreamBase) -> None:
        """Сохранить реализацию интерцептора."""
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
