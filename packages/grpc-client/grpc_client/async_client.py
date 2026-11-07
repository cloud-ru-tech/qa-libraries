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
    """Базовый класс асинхронного gRPC-клиента.

    Наследник объявляет `stub_class` и оборачивает методы сервиса в вызовы `send_*_request`.
    Клиент можно создать как по адресу сервиса, так и поверх готового канала. Канал, созданный
    клиентом, закрывается вместе с ним; переданный извне остается на попечении вызывающего кода.

    Интерцепторы принимаются только вместе с адресом: `grpc.aio` позволяет задать их
    исключительно при создании канала.
    """

    def __init__(self, target: str | grpc.aio.Channel, *options: ClientOption) -> None:
        """Инициализатор.

        :param target: адрес сервиса вида `example.com:443` либо готовый канал
        :param options: опции клиента из модуля `grpc_client.options`
        """
        super().__init__()
        self._apply(options)

        self._owns_channel = not isinstance(target, grpc.aio.Channel)
        if self._owns_channel:
            self._channel = self._create_channel(cast("str", target))
        else:
            # grpc.aio принимает интерцепторы только при создании канала: аналога
            # grpc.intercept_channel() для асинхронного канала в публичном API нет.
            # Молча проглотить их нельзя — авторизация и логирование просто не работали бы.
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
        """Добавить интерцептор для всех поддерживаемых типов вызовов.

        :param interceptor: асинхронный интерцептор grpcio.
        """
        for item in split_async_interceptor(interceptor):
            super().add_interceptor(item)

    @classmethod
    def from_addr(cls, addr: str, *options: ClientOption) -> Self:
        """Создать клиент по адресу сервиса.

        :param addr: адрес сервиса вида `example.com:443`
        :param options: опции клиента из модуля `grpc_client.options`
        :return: асинхронный gRPC-клиент
        """
        return cls(addr, *options)

    @classmethod
    def from_channel(cls, channel: grpc.aio.Channel, *options: ClientOption) -> Self:
        """Создать клиент поверх готового канала.

        Канал не закрывается клиентом: его жизненным циклом управляет вызывающий код.

        :param channel: готовый канал
        :param options: опции клиента из модуля `grpc_client.options`
        :return: асинхронный gRPC-клиент
        """
        return cls(channel, *options)

    async def __aenter__(self) -> Self:
        """Вернуть клиент для асинхронного блока with."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Закрыть принадлежащий клиенту канал."""
        await self.close()

    @property
    def channel(self) -> grpc.aio.Channel:
        """Канал, через который отправляются запросы."""
        return self._channel

    async def close(self, grace: float | None = None) -> None:
        """Закрыть канал, если он был создан клиентом.

        Дожидается интерцепторов с отложенной записью: финальный лог потока пишется отдельной
        задачей. Дренаж выполняется и после закрытия канала — незавершенные потоки обрываются
        именно в этот момент, и задачи их логов появляются только тогда.

        :param grace: время в секундах, отведенное активным вызовам на завершение
        """
        await self._drain_interceptors()

        if self._owns_channel:
            await self._channel.close(grace)

        await self._drain_interceptors()

    async def _drain_interceptors(self) -> None:
        """Дождаться интерцепторов, которые пишут логи отложенными задачами.

        Интерцептор мог быть разложен на адаптеры по типам вызовов, поэтому дренируется
        сама реализация, и каждая — по одному разу.
        """
        # Callback завершения вызова создает задачу лога не мгновенно: даем циклу событий
        # прокрутиться, иначе дренаж не увидит только что оборванный поток.
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
        """Отправить унарный запрос и дождаться ответа.

        :param msg: сообщение запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: ответ на запрос
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
        """Отправить поток сообщений и дождаться одного ответа.

        :param stream: итератор сообщений запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: ответ на запрос
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
        """Отправить запрос и получить поток ответных сообщений.

        :param msg: сообщение запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: поток ответных сообщений
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
        """Отправить поток сообщений и получить поток ответных сообщений.

        :param stream: итератор сообщений запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: поток ответных сообщений
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
        """Дождаться завершения унарного вызова и собрать ответ.

        :param call: выполняющийся вызов
        :return: ответ на запрос
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
