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
    """Базовый класс синхронного gRPC-клиента.

    Клиент можно создать как по адресу сервиса, так и поверх готового канала. Канал, созданный
    клиентом, закрывается вместе с ним; переданный извне остается на попечении вызывающего кода.
    """

    def __init__(self, target: str | grpc.Channel, *options: ClientOption) -> None:
        """Инициализатор.

        :param target: адрес сервиса вида `example.com:443` либо готовый канал
        :param options: опции клиента из модуля `grpc_client.options`
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
        """Создать клиент по адресу сервиса.

        :param addr: адрес сервиса вида `example.com:443`
        :param options: опции клиента из модуля `grpc_client.options`
        :return: gRPC-клиент
        """
        return cls(addr, *options)

    @classmethod
    def from_channel(cls, channel: grpc.Channel, *options: ClientOption) -> Self:
        """Создать клиент поверх готового канала.

        Канал не закрывается клиентом: его жизненным циклом управляет вызывающий код.

        :param channel: готовый канал
        :param options: опции клиента из модуля `grpc_client.options`
        :return: gRPC-клиент
        """
        return cls(channel, *options)

    def __enter__(self) -> Self:
        """Вернуть клиент для блока with."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Закрыть принадлежащий клиенту канал."""
        self.close()

    @property
    def channel(self) -> grpc.Channel:
        """Канал, через который отправляются запросы."""
        return self._channel

    def close(self) -> None:
        """Закрыть канал, если он был создан клиентом."""
        if self._owns_channel:
            self._channel.close()

    def send_unary_unary_request(
        self,
        msg: TRequest,
        method: grpc.UnaryUnaryMultiCallable[TRequest, TResponse],
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
        """Отправить поток сообщений и дождаться одного ответа.

        :param stream: итератор сообщений запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: ответ на запрос
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
        """Отправить запрос и получить поток ответных сообщений.

        Сообщения читаются лениво. Чтобы получить их списком вместе с итоговым статусом,
        вызовите `collect()` у возвращенного объекта.

        :param msg: сообщение запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: поток ответных сообщений
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
        """Отправить поток сообщений и получить поток ответных сообщений.

        :param stream: итератор сообщений запроса
        :param method: метод сервиса из `self.stub`
        :param metadata: метаданные запроса
        :param options: параметры вызова, переопределяющие настройки клиента
        :return: поток ответных сообщений
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
        """Превратить ошибку вызова в ответ.

        Ошибки, не реализующие интерфейс `grpc.Call`, пробрасываются дальше: по ним нельзя
        восстановить ни код статуса, ни метаданные.

        :param error: ошибка gRPC
        :return: ответ без сообщения с кодом статуса ошибки
        """
        if not isinstance(cast("object", error), grpc.Call):
            raise error
        return error
