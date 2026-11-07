from __future__ import annotations

from abc import ABCMeta, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Self, Unpack, cast
from urllib.parse import unquote, urljoin, urlsplit

if TYPE_CHECKING:
    import ssl
    from types import TracebackType

    from httpx._types import (
        AuthTypes,
        TimeoutTypes,
        URLTypes,
    )

    from .types import (
        AsyncSendDecorator,
        AsyncSendMethod,
        AsyncStreamRequestDecorator,
        AsyncStreamRequestMethod,
        RequestHook,
        ResponseHook,
        SendDecorator,
        StreamRequestDecorator,
        SyncSendDecorator,
        SyncSendMethod,
        SyncStreamRequestDecorator,
        SyncStreamRequestMethod,
    )

import httpx
from httpx._client import USE_CLIENT_DEFAULT
from httpx._config import DEFAULT_MAX_REDIRECTS

from .config import HttpClientConfig
from .types import QueryOptions, RequestOptions, SendOptions, StreamOptions

ClientOption = Callable[["BaseHttpClient"], None]


def _reject_unknown_options(options: Mapping[str, object], allowed: frozenset[str]) -> None:
    unknown = set(options).difference(allowed)
    if unknown:
        message = f"Unexpected request options: {', '.join(sorted(unknown))}"
        raise TypeError(message)


def _mark_streaming(request: httpx.Request) -> None:
    extensions = cast("dict[str, object]", request.extensions)
    extensions["is_streaming"] = True


def _ensure_async_hook[T](hook: Callable[[T], Awaitable[None] | None]) -> Callable[[T], Awaitable[None]]:
    """Обернуть синхронный event hook в асинхронную обёртку, если он ещё не async."""

    async def async_hook(message: T) -> None:
        result = hook(message)
        if result is not None:
            await result

    return async_hook


def _resolve_auth(auth: AuthTypes | None, client_auth: AuthTypes | None) -> AuthTypes | None:
    """Выбрать авторизацию запроса.

    Сравнение с None, а не проверка на истинность: у валидного Auth может быть __bool__ == False.
    """
    return auth if auth is not None else client_auth


class BaseHttpClient(metaclass=ABCMeta):
    """Базовый класс HTTP-клиента."""

    DEFAULT_URL_SUFFIX = ""
    DEFAULT_TIMEOUT = httpx.Timeout(60)

    def __init__(
        self,
        base_url: URLTypes,
        *options: ClientOption,
    ) -> None:
        """Применить опции к настройкам до создания транспорта.

        :param base_url: адрес HTTP-сервиса
        :param options: встроенные и пользовательские опции клиента
        """
        self._config = HttpClientConfig(
            base_url=base_url, timeout=self.DEFAULT_TIMEOUT, url_suffix=self.DEFAULT_URL_SUFFIX
        )
        self._configuration_open = True

        for opt in options:
            opt(self)
        self._configuration_open = False

    @property
    def verify(self) -> ssl.SSLContext | str | bool:
        """Вернуть настройку проверки сертификатов транспорта."""
        return self._config.verify

    @verify.setter
    def verify(self, value: ssl.SSLContext | str | bool) -> None:
        self._assert_configuring()
        self._config.verify = value

    @property
    def auth(self) -> AuthTypes | None:
        """Вернуть настройку авторизации транспорта."""
        return self._config.auth

    @auth.setter
    def auth(self, value: AuthTypes | None) -> None:
        self._assert_configuring()
        self._config.auth = value

    @property
    def timeout(self) -> TimeoutTypes:
        """Вернуть таймаут транспорта."""
        return self._config.timeout

    @timeout.setter
    def timeout(self, value: TimeoutTypes) -> None:
        self._assert_configuring()
        self._config.timeout = value

    @property
    def url_suffix(self) -> str:
        """Вернуть префикс относительных путей запросов."""
        return self._config.url_suffix

    @url_suffix.setter
    def url_suffix(self, value: str) -> None:
        self._assert_configuring()
        self._config.url_suffix = value

    def add_request_hook(self, hook: RequestHook, *, prepend: bool = False) -> None:
        """Зарегистрировать хук запроса при применении опций.

        :param hook: обработчик HTTP-запроса
        :param prepend: выполнить хук перед уже зарегистрированными обработчиками
        :raises RuntimeError: создание клиента уже завершено
        """
        self._assert_configuring()
        if prepend:
            self._config.request_hooks.insert(0, hook)
        else:
            self._config.request_hooks.append(hook)

    def add_response_hook(self, hook: ResponseHook) -> None:
        """Зарегистрировать хук ответа при применении опций.

        :param hook: обработчик HTTP-ответа
        :raises RuntimeError: создание клиента уже завершено
        """
        self._assert_configuring()
        self._config.response_hooks.append(hook)

    def add_send_decorator(self, decorator: SendDecorator) -> None:
        """Зарегистрировать декоратор отправки запроса при применении опций.

        :param decorator: декоратор синхронной или асинхронной отправки
        :raises RuntimeError: создание клиента уже завершено
        """
        self._assert_configuring()
        self._config.send_decorators.append(decorator)

    def add_stream_decorator(self, decorator: StreamRequestDecorator) -> None:
        """Зарегистрировать декоратор потокового запроса при применении опций.

        :param decorator: декоратор синхронного или асинхронного контекстного менеджера
        :raises RuntimeError: создание клиента уже завершено
        """
        self._assert_configuring()
        self._config.stream_decorators.append(decorator)

    def enable_redirects(self, max_redirects: int = DEFAULT_MAX_REDIRECTS) -> None:
        """Включить обработку редиректов при применении опций.

        :param max_redirects: максимальное число переходов
        :raises RuntimeError: создание клиента уже завершено
        """
        self._assert_configuring()
        self._config.follow_redirects = True
        self._config.max_redirects = max_redirects

    @property
    def base_url(self) -> httpx.URL:
        """Вернуть базовый URL транспорта."""
        return self.client.base_url

    @property
    @abstractmethod
    def client(self) -> httpx._client.BaseClient:
        """Вернуть синхронный либо асинхронный HTTP-транспорт."""
        ...

    def endpoint(self, path: str) -> str:
        """Построить URL-адрес с учетом суффикса.

        :param path: относительный путь эндпоинта
        :raises ValueError: если путь абсолютный или выходит вверх за пределы суффикса
        :returns: путь с подставленным суффиксом

        >>> assert "api/v1/endpoint" == self.endpoint("api/v1/endpoint")
        >>> self.url_suffix = "/u-api/container-registry/v1"
        >>> assert "/u-api/container-registry/v1/api/v1/endpoint" == self.endpoint("api/v1/endpoint")
        """
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc:
            message = f"endpoint() принимает только относительный путь, получен абсолютный URL: {path!r}"
            raise ValueError(message)
        if ".." in unquote(parsed.path).split("/"):
            message = f"endpoint() не допускает выход вверх по пути: {path!r}"
            raise ValueError(message)

        suffix = self.url_suffix
        if suffix and not suffix.endswith("/"):
            suffix += "/"

        return urljoin(suffix, path.removeprefix("/"))

    def _prepare_request(
        self, method: str, url: URLTypes, options: RequestOptions
    ) -> tuple[httpx.Request, StreamOptions]:
        _reject_unknown_options(options, RequestOptions.__optional_keys__)
        request = self.client.build_request(
            method,
            url,
            content=options.get("content"),
            data=options.get("data"),
            files=options.get("files"),
            json=options.get("json"),
            params=options.get("params"),
            headers=options.get("headers"),
            cookies=options.get("cookies"),
            timeout=options.get("timeout", USE_CLIENT_DEFAULT),
            extensions=options.get("extensions"),
        )
        send_options: StreamOptions = {
            "auth": options.get("auth"),
            "follow_redirects": options.get("follow_redirects"),
            "anonymous": options.get("anonymous", False),
        }
        return request, send_options

    def _assert_configuring(self) -> None:
        if not self._configuration_open:
            message = "Register client configuration through constructor options"
            raise RuntimeError(message)


class HttpClient(BaseHttpClient, metaclass=ABCMeta):
    """Класс HTTP-клиента."""

    def __init__(
        self,
        base_url: URLTypes,
        *options: ClientOption,
    ) -> None:
        """Создать синхронный HTTP-клиент.

        :param base_url: адрес HTTP-сервиса
        :param options: встроенные и пользовательские опции
        """
        super().__init__(base_url, *options)
        self._client = httpx.Client(
            base_url=self._config.base_url,
            auth=self.auth,
            timeout=self.timeout,
            verify=self.verify,
            follow_redirects=self._config.follow_redirects,
            max_redirects=self._config.max_redirects,
            event_hooks={
                "request": self._config.request_hooks,
                "response": self._config.response_hooks,
            },
        )
        self._decorated_send = self._apply_decorators(self._send)
        self._decorated_stream_request = self._apply_stream_request_decorators(self._stream_request)

    @property
    def client(self) -> httpx.Client:
        """Вернуть синхронный HTTP-транспорт."""
        return self._client

    def __enter__(self) -> Self:
        """Открыть пул соединений и вернуть клиент."""
        self.client.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Закрыть пул соединений при выходе из контекста.

        :param exc_type: тип исключения в контексте
        :param exc_val: исключение в контексте
        :param exc_tb: traceback исключения
        """
        self.client.__exit__(exc_type, exc_val, exc_tb)

    def close(self) -> None:
        """Закрыть пул соединений."""
        self.client.close()

    def get(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить GET-запрос."""
        return self.request("GET", url, **options)

    def post(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить POST-запрос."""
        return self.request("POST", url, **options)

    def put(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить PUT-запрос."""
        return self.request("PUT", url, **options)

    def patch(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить PATCH-запрос."""
        return self.request("PATCH", url, **options)

    def delete(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить DELETE-запрос."""
        return self.request("DELETE", url, **options)

    def head(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить HEAD-запрос."""
        return self.request("HEAD", url, **options)

    def options(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить OPTIONS-запрос."""
        return self.request("OPTIONS", url, **options)

    def request(self, method: str, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить HTTP-запрос с произвольным методом."""
        request, send_options = self._prepare_request(method, url, options)
        return self.send(request, **send_options)

    def send(self, request: httpx.Request, **options: Unpack[SendOptions]) -> httpx.Response:
        """Отправить HTTP-запрос."""
        _reject_unknown_options(options, SendOptions.__optional_keys__)
        if options.get("stream", False):
            _mark_streaming(request)
        return self._decorated_send(request, **options)

    def _send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        follow = follow_redirects if follow_redirects is not None else self.client.follow_redirects

        if anonymous:
            return self.client.send(request, stream=stream, auth=None, follow_redirects=follow)
        return self.client.send(
            request,
            stream=stream,
            auth=_resolve_auth(auth, self.client.auth),
            follow_redirects=follow,
        )

    def stream(
        self, method: str, url: URLTypes, **options: Unpack[RequestOptions]
    ) -> AbstractContextManager[httpx.Response]:
        """Выполнить потоковый HTTP-запрос (контракт httpx)."""
        request, send_options = self._prepare_request(method, url, options)
        return self.stream_request(request, **send_options)

    def stream_request(
        self, request: httpx.Request, **options: Unpack[StreamOptions]
    ) -> AbstractContextManager[httpx.Response]:
        """Отправить потоковый HTTP-запрос.

        Возвращает контекстный менеджер для работы с потоковым ответом.

        Пример использования:
        with client.stream_request(request) as response:
        for chunk in response.iter_bytes():
            process(chunk)
        """
        _reject_unknown_options(options, StreamOptions.__optional_keys__)
        return self._decorated_stream_request(request, **options)

    @contextmanager
    def _stream_request(
        self,
        request: httpx.Request,
        *,
        anonymous: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
    ) -> Iterator[httpx.Response]:
        auth_to_use = None if anonymous else _resolve_auth(auth, self.client.auth)
        follow = follow_redirects if follow_redirects is not None else self.client.follow_redirects

        _mark_streaming(request)

        # Отправляем именно переданный Request: пересборка через client.stream()
        # ломала потоковое тело запроса и подсовывала хукам другой объект.
        response = self.client.send(request, stream=True, auth=auth_to_use, follow_redirects=follow)
        try:
            yield response
        finally:
            response.close()

    def _apply_decorators(self, func: SyncSendMethod) -> SyncSendMethod:
        """Применить все декораторы к функции."""
        for decorator in self._config.send_decorators:
            func = cast("SyncSendDecorator", decorator)(func)
        return func

    def _apply_stream_request_decorators(self, func: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        """Применить все декораторы для stream_request к функции."""
        for decorator in self._config.stream_decorators:
            func = cast("SyncStreamRequestDecorator", decorator)(func)
        return func


class AsyncHttpClient(BaseHttpClient, metaclass=ABCMeta):
    """Класс асинхронного HTTP-клиента."""

    def __init__(
        self,
        base_url: URLTypes,
        *options: ClientOption,
    ) -> None:
        """Создать асинхронный HTTP-клиент.

        :param base_url: адрес HTTP-сервиса
        :param options: встроенные и пользовательские опции
        """
        super().__init__(base_url, *options)
        self._config.request_hooks = [_ensure_async_hook(h) for h in self._config.request_hooks]
        self._config.response_hooks = [_ensure_async_hook(h) for h in self._config.response_hooks]
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            auth=self.auth,
            timeout=self.timeout,
            verify=self.verify,
            follow_redirects=self._config.follow_redirects,
            max_redirects=self._config.max_redirects,
            event_hooks={
                "request": self._config.request_hooks,
                "response": self._config.response_hooks,
            },
        )
        self._decorated_send = self._apply_decorators(self._send)
        self._decorated_stream_request = self._apply_stream_request_decorators(self._stream_request)

    @property
    def client(self) -> httpx.AsyncClient:
        """Вернуть асинхронный HTTP-транспорт."""
        return self._client

    async def __aenter__(self) -> Self:
        """Открыть пул соединений и вернуть клиент."""
        await self.client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Закрыть пул соединений при выходе из контекста.

        :param exc_type: тип исключения в контексте
        :param exc_val: исключение в контексте
        :param exc_tb: traceback исключения
        """
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def aclose(self) -> None:
        """Закрыть пул соединений."""
        await self.client.aclose()

    async def get(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить GET-запрос асинхронно."""
        return await self.request("GET", url, **options)

    async def post(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить POST-запрос асинхронно."""
        return await self.request("POST", url, **options)

    async def put(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить PUT-запрос асинхронно."""
        return await self.request("PUT", url, **options)

    async def patch(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить PATCH-запрос асинхронно."""
        return await self.request("PATCH", url, **options)

    async def delete(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить DELETE-запрос асинхронно."""
        return await self.request("DELETE", url, **options)

    async def head(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить HEAD-запрос асинхронно."""
        return await self.request("HEAD", url, **options)

    async def options(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Выполнить OPTIONS-запрос асинхронно."""
        return await self.request("OPTIONS", url, **options)

    async def request(self, method: str, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Выполнить HTTP-запрос с произвольным методом асинхронно."""
        request, send_options = self._prepare_request(method, url, options)
        return await self.send(request, **send_options)

    async def send(self, request: httpx.Request, **options: Unpack[SendOptions]) -> httpx.Response:
        """Отправить HTTP-запрос асинхронно."""
        _reject_unknown_options(options, SendOptions.__optional_keys__)
        if options.get("stream", False):
            _mark_streaming(request)
        return await self._decorated_send(request, **options)

    async def _send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        follow = follow_redirects if follow_redirects is not None else self.client.follow_redirects

        if anonymous:
            return await self.client.send(request, stream=stream, auth=None, follow_redirects=follow)
        return await self.client.send(
            request,
            stream=stream,
            auth=_resolve_auth(auth, self.client.auth),
            follow_redirects=follow,
        )

    def stream(
        self, method: str, url: URLTypes, **options: Unpack[RequestOptions]
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Выполнить потоковый HTTP-запрос асинхронно (контракт httpx)."""
        request, send_options = self._prepare_request(method, url, options)
        return self.stream_request(request, **send_options)

    def stream_request(
        self, request: httpx.Request, **options: Unpack[StreamOptions]
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Отправить потоковый HTTP-запрос асинхронно.

        Возвращает асинхронный контекстный менеджер для работы с потоковым ответом.

        Пример использования:
        async with client.stream_request(request) as response:
        async for chunk in response.aiter_bytes():
            await process(chunk)
        """
        _reject_unknown_options(options, StreamOptions.__optional_keys__)
        return self._decorated_stream_request(request, **options)

    @asynccontextmanager
    async def _stream_request(
        self,
        request: httpx.Request,
        *,
        anonymous: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
    ) -> AsyncIterator[httpx.Response]:
        auth_to_use = None if anonymous else _resolve_auth(auth, self.client.auth)
        follow = follow_redirects if follow_redirects is not None else self.client.follow_redirects

        _mark_streaming(request)

        # Отправляем именно переданный Request: пересборка через client.stream()
        # ломала потоковое тело запроса и подсовывала хукам другой объект.
        response = await self.client.send(request, stream=True, auth=auth_to_use, follow_redirects=follow)
        try:
            yield response
        finally:
            await response.aclose()

    def _apply_decorators(self, func: AsyncSendMethod) -> AsyncSendMethod:
        """Применить все декораторы к функции."""
        for decorator in self._config.send_decorators:
            func = cast("AsyncSendDecorator", decorator)(func)
        return func

    def _apply_stream_request_decorators(self, func: AsyncStreamRequestMethod) -> AsyncStreamRequestMethod:
        """Применить все декораторы для stream_request к функции."""
        for decorator in self._config.stream_decorators:
            func = cast("AsyncStreamRequestDecorator", decorator)(func)
        return func
