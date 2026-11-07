from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING, NamedTuple, cast

import grpc
from grpc_client.interceptors.base import call_detail

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from grpc_client import RequestRecord, ResponseRecord
    from grpc_client.types import MetadataItems


class FakeAuth:
    """Источник токенов для тестов, запоминающий все выданные значения."""

    def __init__(self, prefix: str = "token") -> None:
        """Создать экземпляр с переданными настройками."""
        self._prefix = prefix
        self._counter = count(1)
        self._current: str | None = None
        self.issued: list[str] = []
        self.rejected: list[str] = []

    def token(self) -> str:
        """Выдать текущий токен, выпустив его при первом обращении."""
        if self._current is None:
            self._current = self._issue()
        return self._current

    def refresh(self, rejected_token: str) -> str:
        """Выпустить новый токен взамен отвергнутого."""
        self.rejected.append(rejected_token)
        if self._current is not None and self._current != rejected_token:
            return self._current

        self._current = self._issue()
        return self._current

    def _issue(self) -> str:
        value = f"{self._prefix}-{next(self._counter)}"
        self.issued.append(value)
        return value


class FakeAsyncAuth:
    """Асинхронный источник токенов для тестов."""

    def __init__(self, prefix: str = "async-token") -> None:
        """Создать экземпляр с переданными настройками."""
        self._prefix = prefix
        self._counter = count(1)
        self._current: str | None = None
        self.issued: list[str] = []
        self.rejected: list[str] = []

    async def token(self) -> str:
        """Выдать текущий токен, выпустив его при первом обращении."""
        if self._current is None:
            self._current = self._issue()
        return self._current

    async def refresh(self, rejected_token: str) -> str:
        """Выпустить новый токен взамен отвергнутого."""
        self.rejected.append(rejected_token)
        if self._current is not None and self._current != rejected_token:
            return self._current

        self._current = self._issue()
        return self._current

    def _issue(self) -> str:
        value = f"{self._prefix}-{next(self._counter)}"
        self.issued.append(value)
        return value


class FakeCallDetails(NamedTuple):
    """Параметры вызова для проверки интерцепторов без обращения к сети."""

    method: str = "/example.Service/Method"
    timeout: float | None = None
    metadata: MetadataItems | None = None
    credentials: grpc.CallCredentials | None = None
    wait_for_ready: bool | None = None
    compression: grpc.Compression | None = None


def fake_call_details(metadata: MetadataItems | None = None) -> grpc.ClientCallDetails:
    """Создать параметры синхронного вызова для проверки интерцепторов.

    :param metadata: метаданные запроса
    :return: параметры вызова в том виде, в каком их ждет интерцептор
    """
    return cast("grpc.ClientCallDetails", FakeCallDetails(metadata=metadata))


def fake_aio_call_details(metadata: MetadataItems | None = None) -> grpc.aio.ClientCallDetails:
    """Создать параметры асинхронного вызова для проверки интерцепторов.

    :param metadata: метаданные запроса
    :return: параметры вызова в том виде, в каком их ждет интерцептор
    """
    return cast("grpc.aio.ClientCallDetails", FakeCallDetails(metadata=metadata))


class FakeOutcome:
    """Результат вызова, сообщающий заданный код статуса."""

    def __init__(self, code: grpc.StatusCode, message: object = None) -> None:
        """Создать экземпляр с переданными настройками."""
        self._code = code
        self._message = message

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return ""

    def result(self) -> object:
        return self._message

    def trailing_metadata(self) -> tuple[tuple[str, str | bytes], ...]:
        return ()


class _ContinuationRecorder:
    """Продолжение цепочки интерцепторов, принимающее запросы только с заданным токеном.

    Запоминает параметры каждого вызова, чтобы тест мог проверить не только итоговый статус,
    но и то, какие метаданные ушли в каждой попытке.
    """

    def __init__(self, accepted_token: str | None = None, auth_key: str = "authorization") -> None:
        """Создать экземпляр с переданными настройками."""
        self._accepted_token = accepted_token
        self._auth_key = auth_key
        self.calls: list[object] = []

    def sent_token(self, call_index: int) -> str | None:
        """Получить токен, отправленный в вызове с указанным номером.

        :param call_index: порядковый номер вызова, начиная с нуля
        :return: значение токена без схемы либо None, если заголовка не было
        """
        metadata = dict(call_detail(self.calls[call_index], "metadata", None) or ())
        value = metadata.get(self._auth_key)
        if not isinstance(value, str):
            return None
        return value.removeprefix("Bearer ")


class FakeContinuation(_ContinuationRecorder):
    """Синхронное продолжение цепочки вызовов."""

    def __call__(self, call_details: object, request: object) -> FakeOutcome:
        self.calls.append(call_details)

        if self._accepted_token is not None and self.sent_token(len(self.calls) - 1) == self._accepted_token:
            return FakeOutcome(grpc.StatusCode.OK, request)
        return FakeOutcome(grpc.StatusCode.UNAUTHENTICATED)


class FakeAsyncContinuation(_ContinuationRecorder):
    """Асинхронное продолжение цепочки интерцепторов."""

    async def __call__(self, call_details: object, request: object) -> FakeAsyncOutcome:
        self.calls.append(call_details)

        if self._accepted_token is not None and self.sent_token(len(self.calls) - 1) == self._accepted_token:
            return FakeAsyncOutcome(grpc.StatusCode.OK, request)
        return FakeAsyncOutcome(grpc.StatusCode.UNAUTHENTICATED)

    def sent_token(self, call_index: int) -> str | None:
        """Получить токен, отправленный в вызове с указанным номером."""
        metadata = dict(call_detail(self.calls[call_index], "metadata", None) or ())
        value = metadata.get(self._auth_key)
        if not isinstance(value, str):
            return None
        return value.removeprefix("Bearer ")


class FakeAsyncOutcome:
    """Результат асинхронного вызова, сообщающий заданный код статуса."""

    def __init__(self, code: grpc.StatusCode, message: object = None) -> None:
        """Создать экземпляр с переданными настройками."""
        self._code = code
        self._message = message

    async def code(self) -> grpc.StatusCode:
        return self._code

    async def details(self) -> str:
        return ""

    async def trailing_metadata(self) -> MetadataItems:
        return ()


class FakeAsyncStreamCall:
    """Поддельный потоковый вызов, считающий обращения за сообщениями."""

    def __init__(self, messages_count: int = 0) -> None:
        """Создать экземпляр с переданными настройками."""
        self._messages = [object() for _ in range(messages_count)]
        self.reads = 0
        self.cancelled = False

    def __aiter__(self) -> FakeAsyncStreamCall:
        return self

    async def __anext__(self) -> object:
        self.reads += 1
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    async def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.CANCELLED if self.cancelled else grpc.StatusCode.OK

    async def details(self) -> str:
        return ""

    async def initial_metadata(self) -> MetadataItems:
        return ()

    async def trailing_metadata(self) -> MetadataItems:
        return ()


class FakeStreamCall:
    """Поддельный синхронный потоковый вызов, считающий обращения за сообщениями."""

    def __init__(self, messages_count: int = 0) -> None:
        """Создать экземпляр с переданными настройками."""
        self._messages = [object() for _ in range(messages_count)]
        self.reads = 0
        self.cancelled = False

    def __iter__(self) -> FakeStreamCall:
        return self

    def __next__(self) -> object:
        self.reads += 1
        if not self._messages:
            raise StopIteration
        return self._messages.pop(0)

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.CANCELLED if self.cancelled else grpc.StatusCode.OK

    def details(self) -> str:
        return ""

    def initial_metadata(self) -> tuple[tuple[str, str | bytes], ...]:
        return ()

    def trailing_metadata(self) -> tuple[tuple[str, str | bytes], ...]:
        return ()


class FakeRpcError(grpc.RpcError):
    """Ошибка gRPC, повторяющая публичный интерфейс `grpc.Call`."""

    def __init__(self, code: grpc.StatusCode = grpc.StatusCode.INTERNAL, details: str = "сломалось") -> None:
        """Создать экземпляр с переданными настройками."""
        super().__init__(details)
        self._code = code
        self._details = details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details

    def initial_metadata(self) -> object:
        return ()

    def trailing_metadata(self) -> tuple[()]:
        return ()


class FakeFailingStreamCall:
    """Синхронный поток, отдающий сообщения и затем завершающийся ошибкой."""

    def __init__(self, messages: list[object], error: FakeRpcError) -> None:
        """Создать экземпляр с переданными настройками."""
        self._messages = list(messages)
        self._error = error
        self.cancelled = False

    def __iter__(self) -> FakeFailingStreamCall:
        return self

    def __next__(self) -> object:
        if self._messages:
            return self._messages.pop(0)
        raise self._error

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    def code(self) -> grpc.StatusCode:
        return self._error.code()

    def details(self) -> str:
        return self._error.details()

    def initial_metadata(self) -> tuple[tuple[str, str | bytes], ...]:
        return ()

    def trailing_metadata(self) -> tuple[tuple[str, str | bytes], ...]:
        return ()


class FakeCallbackStreamCall:
    """Поток, вызывающий callback завершения прямо во время чтения сообщения.

    Так воспроизводится гонка между служебным потоком grpcio и читателем: callback приходит
    после того, как сообщение уже получено, но счетчик еще не увеличен.
    """

    def __init__(self, messages_count: int = 1) -> None:
        """Создать экземпляр с переданными настройками."""
        self._messages = [object() for _ in range(messages_count)]
        self._callbacks: list[Callable[[object], None]] = []
        self.cancelled = False

    def add_done_callback(self, callback: Callable[[object], None]) -> None:
        self._callbacks.append(callback)

    def __iter__(self) -> FakeCallbackStreamCall:
        return self

    def __next__(self) -> object:
        if not self._messages:
            self._fire_callbacks()
            raise StopIteration

        message = self._messages.pop(0)
        if not self._messages:
            # Вызов завершился ровно в момент выдачи последнего сообщения.
            self._fire_callbacks()
        return message

    def _fire_callbacks(self) -> None:
        for callback in tuple(self._callbacks):
            self._callbacks.remove(callback)
            callback(self)

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.OK

    def details(self) -> str:
        return ""

    def initial_metadata(self) -> object:
        return ()

    def trailing_metadata(self) -> object:
        return ()


class FakeFailingAsyncStreamCall:
    """Асинхронный поток, отдающий сообщения и затем завершающийся ошибкой."""

    def __init__(self, messages: list[object], error: BaseException) -> None:
        """Создать экземпляр с переданными настройками."""
        self._messages = list(messages)
        self._error = error
        self.cancelled = False

    def __aiter__(self) -> FakeFailingAsyncStreamCall:
        return self

    async def __anext__(self) -> object:
        if self._messages:
            return self._messages.pop(0)
        raise self._error

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    async def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.INTERNAL

    async def details(self) -> str:
        return "сломалось"

    async def initial_metadata(self) -> object:
        return ()

    async def trailing_metadata(self) -> object:
        return ()


class FakeLogSink:
    """Приемник записей о вызовах, складывающий все полученное в списки.

    Уровни хранятся отдельными списками, чтобы тест мог проверить выбор уровня,
    не разбирая при этом саму запись.
    """

    def __init__(self, enabled_levels: Collection[int] | None = None) -> None:
        """Создать экземпляр с переданными настройками."""
        self._enabled_levels = enabled_levels
        self.requests: list[RequestRecord] = []
        self.responses: list[ResponseRecord] = []
        self.request_levels: list[int] = []
        self.response_levels: list[int] = []

    def is_enabled_for(self, level: int) -> bool:
        return self._enabled_levels is None or level in self._enabled_levels

    def write_request(self, level: int, record: RequestRecord) -> None:
        self.request_levels.append(level)
        self.requests.append(record)

    def write_response(self, level: int, record: ResponseRecord) -> None:
        self.response_levels.append(level)
        self.responses.append(record)


class FailingLogSink:
    """Приемник, срывающийся при каждом обращении.

    Так проверяется, что сбой чужого приемника не мешает самому вызову.
    """

    def __init__(self, *, fail_on_check: bool = False) -> None:
        """Создать экземпляр с переданными настройками."""
        self._fail_on_check = fail_on_check

    def is_enabled_for(self, level: int) -> bool:
        if self._fail_on_check:
            message = f"приемник не смог проверить уровень {level}"
            raise RuntimeError(message)
        return True

    def write_request(self, level: int, record: RequestRecord) -> None:
        message = f"приемник не смог записать запрос {record.trace_id} уровнем {level}"
        raise RuntimeError(message)

    def write_response(self, level: int, record: ResponseRecord) -> None:
        message = f"приемник не смог записать ответ {record.trace_id} уровнем {level}"
        raise RuntimeError(message)


class FakeAsyncCallbackStreamCall:
    """Асинхронный поток, вызывающий callback завершения в момент выдачи сообщения."""

    def __init__(self, messages_count: int = 1) -> None:
        """Создать экземпляр с переданными настройками."""
        self._messages = [object() for _ in range(messages_count)]
        self._callbacks: list[Callable[[object], None]] = []
        self.cancelled = False

    def add_done_callback(self, callback: Callable[[object], None]) -> None:
        self._callbacks.append(callback)

    def __aiter__(self) -> FakeAsyncCallbackStreamCall:
        return self

    async def __anext__(self) -> object:
        if not self._messages:
            self._fire_callbacks()
            raise StopAsyncIteration

        message = self._messages.pop(0)
        if not self._messages:
            self._fire_callbacks()
        return message

    def _fire_callbacks(self) -> None:
        for callback in tuple(self._callbacks):
            self._callbacks.remove(callback)
            callback(self)

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    async def code(self) -> grpc.StatusCode:
        return grpc.StatusCode.OK

    async def details(self) -> str:
        return ""

    async def initial_metadata(self) -> object:
        return ()

    async def trailing_metadata(self) -> object:
        return ()
