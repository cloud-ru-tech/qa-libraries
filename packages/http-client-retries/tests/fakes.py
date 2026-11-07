"""Фейки вместо моков: ведут себя как настоящие зависимости, но предсказуемо."""

import io
from collections.abc import AsyncIterator, Awaitable, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from typing import cast, overload

import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient
from tenacity import RetryCallState, Retrying


class FlakyEndpoint:
    """Отдаёт заранее заданную последовательность исходов.

    Исключения возбуждаются, ответы возвращаются. Считает, сколько раз его позвали.
    """

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        """Инициализировать объект."""
        self._outcomes = list(outcomes)
        self.attempts = 0

    def __call__(self, *_args: object, **_kwargs: object) -> httpx.Response:
        self.attempts += 1
        outcome = self._outcomes.pop(0) if self._outcomes else self._outcomes_exhausted()
        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    async def call_async(self, *args: object, **kwargs: object) -> httpx.Response:
        return self(*args, **kwargs)

    def _outcomes_exhausted(self) -> httpx.Response:
        message = f"FlakyEndpoint called {self.attempts} time(s), but no outcomes are left"
        raise AssertionError(message)


class RespondingEndpoint:
    """Всегда отдаёт один и тот же ответ, считая обращения."""

    def __init__(self, response: httpx.Response) -> None:
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        """
        self._response = response
        self.attempts = 0

    def __call__(self, *_args: object, **_kwargs: object) -> httpx.Response:
        self.attempts += 1
        return self._response

    async def call_async(self, *args: object, **kwargs: object) -> httpx.Response:
        return self(*args, **kwargs)


class AsyncCallableEndpoint:
    """Объект с `async def __call__`: не функция, но полноценный асинхронный вызываемый."""

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        """Инициализировать объект."""
        self._outcomes = list(outcomes)
        self.attempts = 0

    async def __call__(self, *_args: object, **_kwargs: object) -> httpx.Response:
        self.attempts += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class CoroutineReturningHook:
    """Обычная функция-хук, которая возвращает корутину. Тип RetryHookT это разрешает."""

    def __init__(self) -> None:
        """Инициализировать объект."""
        self.calls: list[int] = []

    def __call__(self, retry_state: RetryCallState) -> Awaitable[None]:
        return self._record(retry_state)

    async def _record(self, retry_state: RetryCallState) -> None:
        self.calls.append(retry_state.attempt_number)


class CorrelationRecorder:
    """Транспортный обработчик, снимающий значение заголовка в момент отправки.

    Читать заголовки постфактум из `httpx_mock.get_requests()` бесполезно: повторы идут
    по одному и тому же объекту `httpx.Request`, поэтому там окажется только последнее значение.
    """

    def __init__(self, header: str, *outcomes: httpx.Response | Exception) -> None:
        """Инициализировать объект.

        :param header: значение настройки ``header``.
        """
        self._header = header
        self._outcomes = list(outcomes)
        self.captured: list[str | None] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.captured.append(cast("str | None", request.headers.get(self._header)))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class ScriptedTransport(httpx.BaseTransport):
    """Транспорт, отвечающий по сценарию и читающий тело так же, как настоящий.

    `httpx.MockTransport` для проверок тела запроса не годится: он вызывает `request.read()`
    и незаметно буферизует любое тело, из-за чего проблемы переотправки не воспроизводятся.
    """

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        """Инициализировать объект."""
        self._outcomes = list(outcomes)
        self.bodies: list[bytes | str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            self.bodies.append(b"".join(cast("httpx.SyncByteStream", request.stream)))
        except Exception as error:
            self.bodies.append(f"<{type(error).__name__}>")
            message = "тело не читается"
            raise httpx.ConnectError(message, request=request) from error

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    @property
    def attempts(self) -> int:
        return len(self.bodies)


class AsyncScriptedTransport(httpx.AsyncBaseTransport):
    """Асинхронный вариант :class:`ScriptedTransport`."""

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        """Инициализировать объект."""
        self._outcomes = list(outcomes)
        self.bodies: list[bytes | str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            self.bodies.append(b"".join([chunk async for chunk in cast("httpx.AsyncByteStream", request.stream)]))
        except Exception as error:
            self.bodies.append(f"<{type(error).__name__}>")
            message = "тело не читается"
            raise httpx.ConnectError(message, request=request) from error

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    @property
    def attempts(self) -> int:
        return len(self.bodies)


class DisguisedStream(httpx.SyncByteStream):
    """Одноразовый поток, притворяющийся multipart: у него есть атрибут `fields`.

    Проверяет, что классификация тела опирается на тип потока, а не на наличие атрибута.
    """

    fields: tuple[object, ...] = ()

    def __init__(self, payload: bytes) -> None:
        """Инициализировать объект.

        :param payload: значение настройки ``payload``.
        """
        self._payload = payload
        self._used = False

    def __iter__(self) -> Iterator[bytes]:
        if self._used:
            return

        self._used = True
        yield self._payload


class UnseekableFile(io.RawIOBase):
    """Файловый объект без перемотки — так ведут себя пайпы и сетевые потоки."""

    def __init__(self, payload: bytes) -> None:
        """Инициализировать объект.

        :param payload: значение настройки ``payload``.
        """
        self._buffer = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


class ClosableStream(httpx.SyncByteStream):
    """Тело ответа, считающее закрытия."""

    def __init__(self, ledger: dict[str, int], content: bytes = b"payload") -> None:
        """Инициализировать объект.

        :param ledger: значение настройки ``ledger``.
        :param content: значение настройки ``content``.
        """
        self._ledger = ledger
        self._content = content
        ledger["opened"] = ledger.get("opened", 0) + 1

    def __iter__(self) -> Iterator[bytes]:
        yield self._content

    def close(self) -> None:
        self._ledger["closed"] = self._ledger.get("closed", 0) + 1


class ClosableAsyncStream(httpx.AsyncByteStream):
    """Асинхронное тело ответа, считающее закрытия."""

    def __init__(self, ledger: dict[str, int], content: bytes = b"payload") -> None:
        """Инициализировать объект.

        :param ledger: значение настройки ``ledger``.
        :param content: значение настройки ``content``.
        """
        self._ledger = ledger
        self._content = content
        ledger["opened"] = ledger.get("opened", 0) + 1

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content

    async def aclose(self) -> None:
        self._ledger["closed"] = self._ledger.get("closed", 0) + 1


@overload
def attach_transport(client: HttpClient, transport: httpx.BaseTransport) -> AbstractContextManager[HttpClient]: ...


@overload
def attach_transport(
    client: AsyncHttpClient, transport: httpx.AsyncBaseTransport
) -> AbstractAsyncContextManager[AsyncHttpClient]: ...


def attach_transport(
    client: HttpClient | AsyncHttpClient,
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport,
) -> AbstractContextManager[HttpClient] | AbstractAsyncContextManager[AsyncHttpClient]:
    """Подключить сценарный транспорт через публичные обработчики HTTPX.

    :param client: готовый клиент с проверяемыми опциями повторов.
    :param transport: сценарий HTTP-ответов.
    :return: контекст клиента с гарантированным закрытием транспорта.
    """
    if isinstance(client, HttpClient) and isinstance(transport, httpx.BaseTransport):
        return _sync_transport(client, transport)
    if isinstance(client, AsyncHttpClient) and isinstance(transport, httpx.AsyncBaseTransport):
        return _async_transport(client, transport)
    message = "Клиент и транспорт должны использовать один режим выполнения"
    raise TypeError(message)


@contextmanager
def _sync_transport(client: HttpClient, transport: httpx.BaseTransport) -> Iterator[HttpClient]:
    def handle(_self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        return transport.handle_request(request)

    with client, transport, pytest.MonkeyPatch.context() as patch:
        patch.setattr(httpx.HTTPTransport, "handle_request", handle)
        yield client


@asynccontextmanager
async def _async_transport(
    client: AsyncHttpClient, transport: httpx.AsyncBaseTransport
) -> AsyncIterator[AsyncHttpClient]:
    async def handle(_self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return await transport.handle_async_request(request)

    async with client, transport:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
            yield client


class CountingCondition:
    """Условие повтора, отвечающее по заранее заданному списку решений."""

    def __init__(self, decisions: Sequence[bool]) -> None:
        """Инициализировать объект.

        :param decisions: значение настройки ``decisions``.
        """
        self._decisions = list(decisions)
        self.calls = 0

    def __call__(self, _response: httpx.Response) -> bool:
        self.calls += 1
        return self._decisions.pop(0) if self._decisions else False


def retry_state_after(response: httpx.Response) -> RetryCallState:
    """Состояние попытки, завершившейся ответом сервера."""
    state = RetryCallState(Retrying(), None, (), dict[str, object]())
    state.set_result(response)

    return state


def retry_state_after_error(error: BaseException) -> RetryCallState:
    """Состояние попытки, завершившейся исключением."""
    state = RetryCallState(Retrying(), None, (), dict[str, object]())
    state.set_exception((type(error), error, error.__traceback__))

    return state


class RecordingHook:
    """Синхронный before_sleep_hook, запоминающий каждый вызов."""

    def __init__(self) -> None:
        """Инициализировать объект."""
        self.calls: list[RetryCallState] = []

    def __call__(self, retry_state: RetryCallState) -> None:
        self.calls.append(retry_state)


class RecordingAsyncHook:
    """Асинхронный before_sleep_hook, запоминающий каждый вызов."""

    def __init__(self) -> None:
        """Инициализировать объект."""
        self.calls: list[RetryCallState] = []

    async def __call__(self, retry_state: RetryCallState) -> None:
        self.calls.append(retry_state)


class GenericEndpoint:
    """Функция с произвольным типизированным результатом и одним сетевым сбоем."""

    def __init__(self) -> None:
        """Начать сценарий до первой попытки."""
        self.attempts = 0

    def __call__(self, request: httpx.Request, *, label: str) -> tuple[str, int]:
        self.attempts += 1
        if self.attempts == 1:
            message = "temporary generic endpoint failure"
            raise httpx.ConnectError(message, request=request)
        return label, self.attempts
