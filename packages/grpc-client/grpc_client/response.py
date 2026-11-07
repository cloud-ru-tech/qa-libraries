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

# Тип ответного сообщения (Message из сгенерированного pb2 модуля).
TMsg = TypeVar("TMsg")

# Тип разобранного ответного сообщения.
TResult = TypeVar("TResult")


class ResponseOptions(TypedDict, total=False):
    """Дополнительные данные завершившегося вызова."""

    initial_metadata: MetadataItems | None
    trailing_metadata: MetadataItems | None
    error: grpc.RpcError | None


class GRPCResponse[TMsg]:
    """Ответ на унарный запрос к gRPC-серверу."""

    __slots__ = ("_details", "_error", "_initial_metadata", "_message", "_status_code", "_trailing_metadata")

    def __init__(
        self,
        *,
        message: TMsg | None,
        status_code: grpc.StatusCode,
        details: str,
        **options: Unpack[ResponseOptions],
    ) -> None:
        """Создать экземпляр с переданными настройками."""
        self._message = message
        self._status_code = status_code
        self._details = details
        self._initial_metadata = Metadata(options.get("initial_metadata"))
        self._trailing_metadata = Metadata(options.get("trailing_metadata"))
        self._error = options.get("error")

    @classmethod
    def from_call(cls, message: TMsg | None, call: grpc.Call) -> Self:
        """Собрать ответ по завершенному вызову.

        :param message: ответное сообщение
        :param call: объект вызова gRPC
        :return: ответ на запрос
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
        """Собрать ответ по ошибке вызова.

        :param error: ошибка gRPC, реализующая интерфейс `grpc.Call`
        :param message: сообщение, если оно все же есть — например, часть потока,
            успевшая прийти до ошибки
        :return: ответ на запрос
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
        """Код статуса ответа от сервера."""
        return self._status_code

    @property
    def details(self) -> str:
        """Дополнительная информация об ответе, обычно заполняется при неуспешном статусе."""
        return self._details

    @property
    def ok(self) -> bool:
        """Завершился ли запрос успешно."""
        return self._status_code is grpc.StatusCode.OK

    @property
    def initial_metadata(self) -> Metadata:
        """Метаданные, полученные до тела ответа. Ближайший аналог заголовков HTTP."""
        return self._initial_metadata

    @property
    def trailing_metadata(self) -> Metadata:
        """Метаданные, полученные после тела ответа. Здесь сервисы передают подробности ошибок."""
        return self._trailing_metadata

    @property
    def metadata(self) -> Metadata:
        """Синоним `trailing_metadata`."""
        return self._trailing_metadata

    @property
    def error(self) -> grpc.RpcError | None:
        """Исходная ошибка gRPC, если запрос завершился неуспешно."""
        return self._error

    @property
    def error_status(self) -> ErrorStatus | None:
        """Расширенный статус ошибки, переданный сервисом в google.rpc.Status."""
        return error_status_from_metadata(self._trailing_metadata)

    def raise_for_status(self) -> Self:
        """Выбросить исключение, если запрос завершился неуспешно.

        :raises ResponseStatusError: если код ответа отличен от OK
        :return: сам ответ, чтобы вызов можно было продолжить цепочкой
        """
        if not self.ok:
            raise ResponseStatusError(self._status_code, self._details)
        return self

    def message(self) -> TMsg:
        """Получить ответное сообщение.

        :raises MessageUndefinedError: если ответное сообщение отсутствует
        :return: ответное сообщение
        """
        if self._message is None:
            raise MessageUndefinedError(self._status_code, self._details)
        return self._message

    def with_parser(self, parser: Callable[[TMsg], TResult]) -> "GRPCResponseWithParser[TMsg, TResult]":
        """Добавить к ответу функцию преобразования ответного сообщения.

        :param parser: функция преобразования ответного сообщения
        :return: ответ с методом разбора сообщения
        """
        return GRPCResponseWithParser(self, parser)


class GRPCResponseWithParser[TMsg, TResult]:
    """Ответ на запрос к gRPC-серверу с функцией разбора ответного сообщения."""

    __slots__ = ("_parser", "_response")

    def __init__(self, response: GRPCResponse[TMsg], parser: Callable[[TMsg], TResult]) -> None:
        """Создать экземпляр с переданными настройками."""
        self._response = response
        self._parser = parser

    @property
    def status_code(self) -> grpc.StatusCode:
        """Код статуса ответа от сервера."""
        return self._response.status_code

    @property
    def details(self) -> str:
        """Дополнительная информация об ответе, обычно заполняется при неуспешном статусе."""
        return self._response.details

    @property
    def ok(self) -> bool:
        """Завершился ли запрос успешно."""
        return self._response.ok

    @property
    def initial_metadata(self) -> Metadata:
        """Метаданные, полученные до тела ответа."""
        return self._response.initial_metadata

    @property
    def trailing_metadata(self) -> Metadata:
        """Метаданные, полученные после тела ответа."""
        return self._response.trailing_metadata

    @property
    def metadata(self) -> Metadata:
        """Синоним `trailing_metadata`."""
        return self._response.metadata

    @property
    def error(self) -> grpc.RpcError | None:
        """Исходная ошибка gRPC, если запрос завершился неуспешно."""
        return self._response.error

    @property
    def error_status(self) -> ErrorStatus | None:
        """Расширенный статус ошибки, переданный сервисом в google.rpc.Status."""
        return self._response.error_status

    def raise_for_status(self) -> Self:
        """Выбросить исключение, если запрос завершился неуспешно.

        :raises ResponseStatusError: если код ответа отличен от OK
        :return: сам ответ, чтобы вызов можно было продолжить цепочкой
        """
        self._response.raise_for_status()
        return self

    def message(self) -> TMsg:
        """Получить ответное сообщение.

        :raises MessageUndefinedError: если ответное сообщение отсутствует
        :return: ответное сообщение
        """
        return self._response.message()

    def parse(self) -> TResult:
        """Разобрать ответное сообщение.

        :raises MessageUndefinedError: если ответное сообщение отсутствует
        :return: результат работы функции разбора
        """
        return self._parser(self.message())


class GRPCStreamResponse[TMsg]:
    """Ответ на стриминговый запрос к gRPC-серверу.

    Сообщения читаются лениво, по мере поступления от сервера, и не буферизуются.
    Итоговый статус и trailing-метаданные сервер сообщает только после завершения потока,
    поэтому до окончания чтения они недоступны.

    Поток удерживает вызов открытым, поэтому его следует либо дочитать, либо закрыть.
    Проще всего использовать как контекстный менеджер: незавершенный вызов будет отменен на выходе.
    """

    __slots__ = ("_call", "_consumed", "_iterator")

    def __init__(self, call: grpc.Call) -> None:
        """Создать экземпляр с переданными настройками."""
        self._call = call
        self._iterator = cast("Iterator[TMsg]", call)
        self._consumed = False

    def __iter__(self) -> Iterator[TMsg]:
        """Получить итератор значений."""
        if self._consumed:
            raise StreamConsumedError

        # Поток считается прочитанным только когда он действительно закончился: при досрочном
        # выходе из итерации вызов еще жив, и его нужно отменить.
        try:
            yield from self._iterator
        except grpc.RpcError:
            self._consumed = True
            raise

        self._consumed = True

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
        self.cancel()

    @property
    def initial_metadata(self) -> Metadata:
        """Метаданные, полученные до тела ответа."""
        return Metadata(_safe_metadata(self._call.initial_metadata))

    @property
    def trailing_metadata(self) -> Metadata:
        """Метаданные, полученные после завершения потока.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        self._ensure_consumed("trailing_metadata")
        return Metadata(_safe_metadata(self._call.trailing_metadata))

    @property
    def status_code(self) -> grpc.StatusCode:
        """Итоговый код статуса потока.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        self._ensure_consumed("status_code")
        return cast("grpc.StatusCode | None", self._call.code()) or grpc.StatusCode.UNKNOWN

    @property
    def details(self) -> str:
        """Дополнительная информация о завершении потока.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        self._ensure_consumed("details")
        return self._call.details() or ""

    @property
    def ok(self) -> bool:
        """Завершился ли поток успешно.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        return self.status_code is grpc.StatusCode.OK

    def cancel(self) -> None:
        """Отменить вызов, если он еще не завершен."""
        if not self._consumed:
            cast("Callable[[], bool]", self._call.cancel)()
            self._consumed = True

    def collect(self, limit: int | None = None) -> GRPCResponse[list[TMsg]]:
        """Прочитать поток целиком и собрать сообщения в список.

        Ошибка сервера не выбрасывается, а превращается в ответ с соответствующим кодом статуса.

        :param limit: максимальное количество сообщений; по достижении предела вызов отменяется,
            `0` — не читать ничего и сразу отменить вызов
        :raises StreamConsumedError: если поток уже прочитан
        :raises ValueError: если ограничение отрицательное
        :return: ответ со списком полученных сообщений
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
            # Сообщения, пришедшие до ошибки, остаются полезными: по ним видно,
            # на каком месте поток оборвался.
            return GRPCResponse.from_error(error, messages)

        return GRPCResponse.from_call(messages, self._call)

    def _ensure_consumed(self, attribute: str) -> None:
        if not self._consumed:
            raise StreamNotConsumedError(attribute)


class AsyncGRPCStreamResponse[TMsg]:
    """Ответ на стриминговый запрос к gRPC-серверу в асинхронном клиенте.

    Ведет себя так же, как `GRPCStreamResponse`, но читается асинхронно.
    """

    __slots__ = ("_call", "_cancelled_by_client", "_consumed", "_iterator")

    def __init__(self, call: grpc.aio.Call) -> None:
        """Создать экземпляр с переданными настройками."""
        self._call = call
        self._iterator = cast("AsyncIterator[TMsg]", call)
        self._consumed = False
        self._cancelled_by_client = False

    async def __aiter__(self) -> AsyncIterator[TMsg]:
        """Получить асинхронный итератор сообщений."""
        if self._consumed:
            raise StreamConsumedError

        # Поток считается прочитанным только когда он действительно закончился: при досрочном
        # выходе из итерации вызов еще жив, и его нужно отменить.
        try:
            async for message in self._iterator:
                yield message
        except grpc.aio.AioRpcError:
            self._consumed = True
            raise
        except asyncio.CancelledError:
            # Отмену не поглощаем, но поток после нее терминален: сам вызов тоже отменяем,
            # иначе он остался бы висеть, а его статус — недоступным.
            self._cancelled_by_client = bool(self._call.cancel())
            self._consumed = True
            raise

        self._consumed = True

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
        self.cancel()

    async def initial_metadata(self) -> Metadata:
        """Получить метаданные, пришедшие до тела ответа."""
        return Metadata(aio_metadata_items(await self._call.initial_metadata()))

    async def trailing_metadata(self) -> Metadata:
        """Получить метаданные, пришедшие после завершения потока.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        self._ensure_consumed("trailing_metadata")
        return Metadata(aio_metadata_items(await self._call.trailing_metadata()))

    async def status_code(self) -> grpc.StatusCode:
        """Получить итоговый код статуса потока.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        self._ensure_consumed("status_code")
        return cast("grpc.StatusCode | None", await self._call.code()) or grpc.StatusCode.UNKNOWN

    async def details(self) -> str:
        """Получить дополнительную информацию о завершении потока.

        :raises StreamNotConsumedError: если поток еще не прочитан до конца
        """
        self._ensure_consumed("details")
        return await self._call.details() or ""

    def cancel(self) -> None:
        """Отменить вызов, если он еще не завершен."""
        if not self._consumed:
            # cancel() отвечает False, если вызов уже завершился сам: тогда его настоящий
            # статус важнее, и подменять его на CANCELLED нельзя.
            self._cancelled_by_client = bool(self._call.cancel())
            self._consumed = True

    async def collect(self, limit: int | None = None) -> GRPCResponse[list[TMsg]]:
        """Прочитать поток целиком и собрать сообщения в список.

        Ошибка сервера не выбрасывается, а превращается в ответ с соответствующим кодом статуса.

        :param limit: максимальное количество сообщений; по достижении предела вызов отменяется,
            `0` — не читать ничего и сразу отменить вызов
        :raises StreamConsumedError: если поток уже прочитан
        :raises ValueError: если ограничение отрицательное
        :return: ответ со списком полученных сообщений
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
            # Сообщения, пришедшие до ошибки, остаются полезными.
            return GRPCResponse.from_error(error, messages)

        return await self._response_with(messages)

    async def _response_with(self, messages: list[TMsg]) -> GRPCResponse[list[TMsg]]:
        """Собрать ответ по фактическому состоянию вызова.

        Если поток отменил сам клиент — по достижении предела или нулевым пределом, — статус
        известен заранее. Читать его у вызова нельзя: обращение к отмененному вызову подняло бы
        `CancelledError`, а перехватывать его здесь нельзя — так проглатывалась бы и отмена
        вызывающей задачи, ломая `asyncio.timeout` и корректное завершение приложения.
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
    """Проверить ограничение на количество читаемых сообщений.

    :param limit: максимальное количество сообщений
    :raises ValueError: если ограничение отрицательное
    """
    if limit is not None and limit < 0:
        message = f"Ограничение на количество сообщений не может быть отрицательным, получено {limit}"
        raise ValueError(message)


def _safe_metadata(getter: Callable[[], MetadataItems | None]) -> MetadataItems:
    """Прочитать метаданные вызова, не падая на реализациях, которые их не отдают.

    :param getter: метод вызова, возвращающий метаданные
    :return: метаданные либо пустая последовательность
    """
    try:
        return getter() or ()
    except (AttributeError, ValueError, grpc.RpcError):
        return ()
