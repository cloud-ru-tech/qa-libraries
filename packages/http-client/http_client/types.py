from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Protocol, TypedDict

import httpx
from httpx._client import UseClientDefault
from httpx._types import (
    AuthTypes,
    CookieTypes,
    HeaderTypes,
    QueryParamTypes,
    RequestContent,
    RequestFiles,
    TimeoutTypes,
)

type EventHook[T = object] = Callable[[T], Awaitable[None] | None]
type RequestHook = EventHook[httpx.Request]
type ResponseHook = EventHook[httpx.Response]
type RequestData = Mapping[str, object]


class LoggingOptions(TypedDict, total=False):
    """Именованные настройки логирования отдельного HTTP-клиента."""

    sanitize_keys: Sequence[str] | None
    json_indent: int | None
    use_line_breaks: bool | None
    log_level: int | None
    use_default_sanitize_keys: bool


class QueryOptions(TypedDict, total=False):
    """Именованные параметры HTTP-запроса без тела."""

    params: QueryParamTypes | None
    headers: HeaderTypes | None
    cookies: CookieTypes | None
    auth: AuthTypes | None
    follow_redirects: bool | None
    timeout: TimeoutTypes | UseClientDefault
    extensions: dict[str, object] | None
    anonymous: bool


class RequestOptions(QueryOptions, total=False):
    """Именованные параметры HTTP-запроса с телом."""

    content: RequestContent | None
    data: RequestData | None
    files: RequestFiles | None
    json: object


class StreamOptions(TypedDict, total=False):
    """Параметры отправки готового запроса в потоковом режиме."""

    auth: AuthTypes | None
    follow_redirects: bool | None
    anonymous: bool


class SendOptions(StreamOptions, total=False):
    """Параметры отправки готового HTTP-запроса."""

    stream: bool


class SyncSendMethod(Protocol):
    """Протокол для синхронного метода send."""

    def __call__(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        """Отправить готовый HTTP-запрос и вернуть ответ."""
        ...


class AsyncSendMethod(Protocol):
    """Протокол для асинхронного метода send."""

    async def __call__(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        """Асинхронно отправить готовый HTTP-запрос и вернуть ответ."""
        ...


class SyncStreamRequestMethod(Protocol):
    """Протокол для синхронного метода stream_request."""

    def __call__(
        self,
        request: httpx.Request,
        *,
        anonymous: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
    ) -> AbstractContextManager[httpx.Response]:
        """Открыть контекст потокового HTTP-ответа."""
        ...


class AsyncStreamRequestMethod(Protocol):
    """Протокол для асинхронного метода stream_request."""

    def __call__(
        self,
        request: httpx.Request,
        *,
        anonymous: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Открыть асинхронный контекст потокового HTTP-ответа."""
        ...


# Типы для декораторов методов send
SyncSendDecorator = Callable[[SyncSendMethod], SyncSendMethod]
AsyncSendDecorator = Callable[[AsyncSendMethod], AsyncSendMethod]

SendDecorator = SyncSendDecorator | AsyncSendDecorator

# Типы для декораторов методов stream_request
SyncStreamRequestDecorator = Callable[[SyncStreamRequestMethod], SyncStreamRequestMethod]
AsyncStreamRequestDecorator = Callable[[AsyncStreamRequestMethod], AsyncStreamRequestMethod]

StreamRequestDecorator = SyncStreamRequestDecorator | AsyncStreamRequestDecorator
