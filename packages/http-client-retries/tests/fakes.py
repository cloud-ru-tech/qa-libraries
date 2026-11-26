"""Fakes rather than mocks: behave like real dependencies, but predictably."""

import io
from collections.abc import AsyncIterator, Awaitable, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from typing import cast, overload

import httpx2
import pytest
from http_client import AsyncHttpClient, HttpClient
from tenacity import RetryCallState, Retrying


class FlakyEndpoint:
    """Return a predefined sequence of outcomes.

    Raise exceptions and return responses while counting calls.
    """

    def __init__(self, *outcomes: httpx2.Response | Exception) -> None:
        """Initialize the object."""
        self._outcomes = list(outcomes)
        self.attempts = 0

    def __call__(self, *_args: object, **_kwargs: object) -> httpx2.Response:
        self.attempts += 1
        outcome = self._outcomes.pop(0) if self._outcomes else self._outcomes_exhausted()
        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    async def call_async(self, *args: object, **kwargs: object) -> httpx2.Response:
        return self(*args, **kwargs)

    def _outcomes_exhausted(self) -> httpx2.Response:
        message = f"FlakyEndpoint called {self.attempts} time(s), but no outcomes are left"
        raise AssertionError(message)


class RespondingEndpoint:
    """Return the same response every time while counting calls."""

    def __init__(self, response: httpx2.Response) -> None:
        """Initialize the object.

        :param response: Value of ``response``.
        """
        self._response = response
        self.attempts = 0

    def __call__(self, *_args: object, **_kwargs: object) -> httpx2.Response:
        self.attempts += 1
        return self._response

    async def call_async(self, *args: object, **kwargs: object) -> httpx2.Response:
        return self(*args, **kwargs)


class AsyncCallableEndpoint:
    """Object with `async def __call__`: not a function, but a valid asynchronous callable."""

    def __init__(self, *outcomes: httpx2.Response | Exception) -> None:
        """Initialize the object."""
        self._outcomes = list(outcomes)
        self.attempts = 0

    async def __call__(self, *_args: object, **_kwargs: object) -> httpx2.Response:
        self.attempts += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class CoroutineReturningHook:
    """Regular hook function that returns a coroutine, as allowed by RetryHookT."""

    def __init__(self) -> None:
        """Initialize the object."""
        self.calls: list[int] = []

    def __call__(self, retry_state: RetryCallState) -> Awaitable[None]:
        return self._record(retry_state)

    async def _record(self, retry_state: RetryCallState) -> None:
        self.calls.append(retry_state.attempt_number)


class CorrelationRecorder:
    """Transport handler that captures a header value at send time.

    Reading headers afterward from `httpx2_mock.get_requests()` is useless: retries use
    the same `httpx2.Request` object, so only the latest value remains there.
    """

    def __init__(self, header: str, *outcomes: httpx2.Response | Exception) -> None:
        """Initialize the object.

        :param header: Value of ``header``.
        """
        self._header = header
        self._outcomes = list(outcomes)
        self.captured: list[str | None] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.captured.append(request.headers.get(self._header))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class ScriptedTransport(httpx2.BaseTransport):
    """Transport with scripted responses that reads bodies like a real transport.

    `httpx2.MockTransport` cannot test request bodies: it calls `request.read()`
    and silently buffers every body, hiding replay problems.
    """

    def __init__(self, *outcomes: httpx2.Response | Exception) -> None:
        """Initialize the object."""
        self._outcomes = list(outcomes)
        self.bodies: list[bytes | str] = []

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            self.bodies.append(b"".join(cast("httpx2.SyncByteStream", request.stream)))
        except Exception as error:
            self.bodies.append(f"<{type(error).__name__}>")
            message = "тело не читается"
            raise httpx2.ConnectError(message, request=request) from error

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    @property
    def attempts(self) -> int:
        return len(self.bodies)


class AsyncScriptedTransport(httpx2.AsyncBaseTransport):
    """Asynchronous version of :class:`ScriptedTransport`."""

    def __init__(self, *outcomes: httpx2.Response | Exception) -> None:
        """Initialize the object."""
        self._outcomes = list(outcomes)
        self.bodies: list[bytes | str] = []

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            self.bodies.append(b"".join([chunk async for chunk in cast("httpx2.AsyncByteStream", request.stream)]))
        except Exception as error:
            self.bodies.append(f"<{type(error).__name__}>")
            message = "тело не читается"
            raise httpx2.ConnectError(message, request=request) from error

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    @property
    def attempts(self) -> int:
        return len(self.bodies)


class DisguisedStream(httpx2.SyncByteStream):
    """One-shot stream pretending to be multipart by exposing a `fields` attribute.

    Check that body classification uses the stream type rather than the presence of an attribute.
    """

    fields: tuple[object, ...] = ()

    def __init__(self, payload: bytes) -> None:
        """Initialize the object.

        :param payload: Value of ``payload``.
        """
        self._payload = payload
        self._used = False

    def __iter__(self) -> Iterator[bytes]:
        if self._used:
            return

        self._used = True
        yield self._payload


class UnseekableFile(io.RawIOBase):
    """Non-seekable file object, like pipes and network streams."""

    def __init__(self, payload: bytes) -> None:
        """Initialize the object.

        :param payload: Value of ``payload``.
        """
        self._buffer = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


class ClosableStream(httpx2.SyncByteStream):
    """Response body that counts close calls."""

    def __init__(self, ledger: dict[str, int], content: bytes = b"payload") -> None:
        """Initialize the object.

        :param ledger: Value of ``ledger``.
        :param content: Value of ``content``.
        """
        self._ledger = ledger
        self._content = content
        ledger["opened"] = ledger.get("opened", 0) + 1

    def __iter__(self) -> Iterator[bytes]:
        yield self._content

    def close(self) -> None:
        self._ledger["closed"] = self._ledger.get("closed", 0) + 1


class ClosableAsyncStream(httpx2.AsyncByteStream):
    """Asynchronous response body that counts close calls."""

    def __init__(self, ledger: dict[str, int], content: bytes = b"payload") -> None:
        """Initialize the object.

        :param ledger: Value of ``ledger``.
        :param content: Value of ``content``.
        """
        self._ledger = ledger
        self._content = content
        ledger["opened"] = ledger.get("opened", 0) + 1

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content

    async def aclose(self) -> None:
        self._ledger["closed"] = self._ledger.get("closed", 0) + 1


@overload
def attach_transport(client: HttpClient, transport: httpx2.BaseTransport) -> AbstractContextManager[HttpClient]: ...


@overload
def attach_transport(
    client: AsyncHttpClient, transport: httpx2.AsyncBaseTransport
) -> AbstractAsyncContextManager[AsyncHttpClient]: ...


def attach_transport(
    client: HttpClient | AsyncHttpClient,
    transport: httpx2.BaseTransport | httpx2.AsyncBaseTransport,
) -> AbstractContextManager[HttpClient] | AbstractAsyncContextManager[AsyncHttpClient]:
    """Attach a scripted transport through public HTTPX2 handlers.

    :param client: Ready client with the retry options under test.
    :param transport: Scripted HTTP responses.
    :return: Client context that guarantees transport closure.
    """
    if isinstance(client, HttpClient) and isinstance(transport, httpx2.BaseTransport):
        return _sync_transport(client, transport)
    if isinstance(client, AsyncHttpClient) and isinstance(transport, httpx2.AsyncBaseTransport):
        return _async_transport(client, transport)
    message = "Клиент и транспорт должны использовать один режим выполнения"
    raise TypeError(message)


@contextmanager
def _sync_transport(client: HttpClient, transport: httpx2.BaseTransport) -> Iterator[HttpClient]:
    def handle(_self: httpx2.HTTPTransport, request: httpx2.Request) -> httpx2.Response:
        return transport.handle_request(request)

    with client, transport, pytest.MonkeyPatch.context() as patch:
        patch.setattr(httpx2.HTTPTransport, "handle_request", handle)
        yield client


@asynccontextmanager
async def _async_transport(
    client: AsyncHttpClient, transport: httpx2.AsyncBaseTransport
) -> AsyncIterator[AsyncHttpClient]:
    async def handle(_self: httpx2.AsyncHTTPTransport, request: httpx2.Request) -> httpx2.Response:
        return await transport.handle_async_request(request)

    async with client, transport:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", handle)
            yield client


class CountingCondition:
    """Retry condition that returns a predefined sequence of decisions."""

    def __init__(self, decisions: Sequence[bool]) -> None:
        """Initialize the object.

        :param decisions: Value of ``decisions``.
        """
        self._decisions = list(decisions)
        self.calls = 0

    def __call__(self, _response: httpx2.Response) -> bool:
        self.calls += 1
        return self._decisions.pop(0) if self._decisions else False


def retry_state_after(response: httpx2.Response) -> RetryCallState:
    """State of an attempt that received a server response."""
    state = RetryCallState(Retrying(), None, (), dict[str, object]())
    state.set_result(response)

    return state


def retry_state_after_error(error: BaseException) -> RetryCallState:
    """State of an attempt that raised an exception."""
    state = RetryCallState(Retrying(), None, (), dict[str, object]())
    state.set_exception((type(error), error, error.__traceback__))

    return state


class RecordingHook:
    """Synchronous before_sleep_hook that records each call."""

    def __init__(self) -> None:
        """Initialize the object."""
        self.calls: list[RetryCallState] = []

    def __call__(self, retry_state: RetryCallState) -> None:
        self.calls.append(retry_state)


class RecordingAsyncHook:
    """Asynchronous before_sleep_hook that records each call."""

    def __init__(self) -> None:
        """Initialize the object."""
        self.calls: list[RetryCallState] = []

    async def __call__(self, retry_state: RetryCallState) -> None:
        self.calls.append(retry_state)


class GenericEndpoint:
    """Function with an arbitrary typed result and one network failure."""

    def __init__(self) -> None:
        """Initialize the scenario before the first attempt."""
        self.attempts = 0

    def __call__(self, request: httpx2.Request, *, label: str) -> tuple[str, int]:
        self.attempts += 1
        if self.attempts == 1:
            message = "temporary generic endpoint failure"
            raise httpx2.ConnectError(message, request=request)
        return label, self.attempts
