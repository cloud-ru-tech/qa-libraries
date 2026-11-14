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
    """Wrap a synchronous event hook in an asynchronous wrapper if needed."""

    async def async_hook(message: T) -> None:
        result = hook(message)
        if result is not None:
            await result

    return async_hook


def _resolve_auth(auth: AuthTypes | None, client_auth: AuthTypes | None) -> AuthTypes | None:
    """Select request authentication.

    Compare with None rather than checking truthiness: a valid Auth may have __bool__ == False.
    """
    return auth if auth is not None else client_auth


class BaseHttpClient(metaclass=ABCMeta):
    """Base HTTP client class."""

    DEFAULT_URL_SUFFIX = ""
    DEFAULT_TIMEOUT = httpx.Timeout(60)

    def __init__(
        self,
        base_url: URLTypes,
        *options: ClientOption,
    ) -> None:
        """Apply options to the settings before creating the transport.

        :param base_url: HTTP service address
        :param options: Built-in and custom client options
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
        """Return the transport certificate verification setting."""
        return self._config.verify

    @verify.setter
    def verify(self, value: ssl.SSLContext | str | bool) -> None:
        self._assert_configuring()
        self._config.verify = value

    @property
    def auth(self) -> AuthTypes | None:
        """Return the transport authentication setting."""
        return self._config.auth

    @auth.setter
    def auth(self, value: AuthTypes | None) -> None:
        self._assert_configuring()
        self._config.auth = value

    @property
    def timeout(self) -> TimeoutTypes:
        """Return the transport timeout."""
        return self._config.timeout

    @timeout.setter
    def timeout(self, value: TimeoutTypes) -> None:
        self._assert_configuring()
        self._config.timeout = value

    @property
    def url_suffix(self) -> str:
        """Return the prefix for relative request paths."""
        return self._config.url_suffix

    @url_suffix.setter
    def url_suffix(self, value: str) -> None:
        self._assert_configuring()
        self._config.url_suffix = value

    def add_request_hook(self, hook: RequestHook, *, prepend: bool = False) -> None:
        """Register a request hook while applying options.

        :param hook: HTTP request handler
        :param prepend: Run the hook before previously registered handlers
        :raises RuntimeError: Client initialization has already finished
        """
        self._assert_configuring()
        if prepend:
            self._config.request_hooks.insert(0, hook)
        else:
            self._config.request_hooks.append(hook)

    def add_response_hook(self, hook: ResponseHook) -> None:
        """Register a response hook while applying options.

        :param hook: HTTP response handler
        :raises RuntimeError: Client initialization has already finished
        """
        self._assert_configuring()
        self._config.response_hooks.append(hook)

    def add_send_decorator(self, decorator: SendDecorator) -> None:
        """Register a request send decorator while applying options.

        :param decorator: Synchronous or asynchronous send decorator
        :raises RuntimeError: Client initialization has already finished
        """
        self._assert_configuring()
        self._config.send_decorators.append(decorator)

    def add_stream_decorator(self, decorator: StreamRequestDecorator) -> None:
        """Register a streaming request decorator while applying options.

        :param decorator: Synchronous or asynchronous context manager decorator
        :raises RuntimeError: Client initialization has already finished
        """
        self._assert_configuring()
        self._config.stream_decorators.append(decorator)

    def enable_redirects(self, max_redirects: int = DEFAULT_MAX_REDIRECTS) -> None:
        """Enable redirects while applying options.

        :param max_redirects: Maximum number of redirects
        :raises RuntimeError: Client initialization has already finished
        """
        self._assert_configuring()
        self._config.follow_redirects = True
        self._config.max_redirects = max_redirects

    @property
    def base_url(self) -> httpx.URL:
        """Return the transport base URL."""
        return self.client.base_url

    @property
    @abstractmethod
    def client(self) -> httpx._client.BaseClient:
        """Return the synchronous or asynchronous HTTP transport."""
        ...

    def endpoint(self, path: str) -> str:
        """Build a URL using the suffix.

        :param path: Relative endpoint path
        :raises ValueError: If the path is absolute or traverses above the suffix
        :returns: Path with the suffix applied

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
    """HTTP client class."""

    def __init__(
        self,
        base_url: URLTypes,
        *options: ClientOption,
    ) -> None:
        """Create a synchronous HTTP client.

        :param base_url: HTTP service address
        :param options: Built-in and custom options
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
        """Return the synchronous HTTP transport."""
        return self._client

    def __enter__(self) -> Self:
        """Open the connection pool and return the client."""
        self.client.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the connection pool when leaving the context.

        :param exc_type: Type of the exception in the context
        :param exc_val: Exception in the context
        :param exc_tb: Exception traceback
        """
        self.client.__exit__(exc_type, exc_val, exc_tb)

    def close(self) -> None:
        """Close the connection pool."""
        self.client.close()

    def get(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send a GET request."""
        return self.request("GET", url, **options)

    def post(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send a POST request."""
        return self.request("POST", url, **options)

    def put(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send a PUT request."""
        return self.request("PUT", url, **options)

    def patch(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send a PATCH request."""
        return self.request("PATCH", url, **options)

    def delete(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send a DELETE request."""
        return self.request("DELETE", url, **options)

    def head(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send a HEAD request."""
        return self.request("HEAD", url, **options)

    def options(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send an OPTIONS request."""
        return self.request("OPTIONS", url, **options)

    def request(self, method: str, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send an HTTP request with an arbitrary method."""
        request, send_options = self._prepare_request(method, url, options)
        return self.send(request, **send_options)

    def send(self, request: httpx.Request, **options: Unpack[SendOptions]) -> httpx.Response:
        """Send an HTTP request."""
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
        """Send a streaming HTTP request using the httpx contract."""
        request, send_options = self._prepare_request(method, url, options)
        return self.stream_request(request, **send_options)

    def stream_request(
        self, request: httpx.Request, **options: Unpack[StreamOptions]
    ) -> AbstractContextManager[httpx.Response]:
        """Send a streaming HTTP request.

        Return a context manager for accessing the streaming response.

        Usage example:
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

        # Send the supplied Request: rebuilding it with client.stream()
        # broke streaming request bodies and passed a different object to hooks.
        response = self.client.send(request, stream=True, auth=auth_to_use, follow_redirects=follow)
        try:
            yield response
        finally:
            response.close()

    def _apply_decorators(self, func: SyncSendMethod) -> SyncSendMethod:
        """Apply all decorators to the function."""
        for decorator in self._config.send_decorators:
            func = cast("SyncSendDecorator", decorator)(func)
        return func

    def _apply_stream_request_decorators(self, func: SyncStreamRequestMethod) -> SyncStreamRequestMethod:
        """Apply all stream_request decorators to the function."""
        for decorator in self._config.stream_decorators:
            func = cast("SyncStreamRequestDecorator", decorator)(func)
        return func


class AsyncHttpClient(BaseHttpClient, metaclass=ABCMeta):
    """Asynchronous HTTP client."""

    def __init__(
        self,
        base_url: URLTypes,
        *options: ClientOption,
    ) -> None:
        """Create an asynchronous HTTP client.

        :param base_url: HTTP service address
        :param options: Built-in and custom options
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
        """Return the asynchronous HTTP transport."""
        return self._client

    async def __aenter__(self) -> Self:
        """Open the connection pool and return the client."""
        await self.client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the connection pool when leaving the context.

        :param exc_type: Type of the exception in the context
        :param exc_val: Exception in the context
        :param exc_tb: Exception traceback
        """
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def aclose(self) -> None:
        """Close the connection pool."""
        await self.client.aclose()

    async def get(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send a GET request asynchronously."""
        return await self.request("GET", url, **options)

    async def post(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send a POST request asynchronously."""
        return await self.request("POST", url, **options)

    async def put(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send a PUT request asynchronously."""
        return await self.request("PUT", url, **options)

    async def patch(self, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send a PATCH request asynchronously."""
        return await self.request("PATCH", url, **options)

    async def delete(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send a DELETE request asynchronously."""
        return await self.request("DELETE", url, **options)

    async def head(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send a HEAD request asynchronously."""
        return await self.request("HEAD", url, **options)

    async def options(self, url: URLTypes, **options: Unpack[QueryOptions]) -> httpx.Response:
        """Send an OPTIONS request asynchronously."""
        return await self.request("OPTIONS", url, **options)

    async def request(self, method: str, url: URLTypes, **options: Unpack[RequestOptions]) -> httpx.Response:
        """Send an HTTP request with an arbitrary method asynchronously."""
        request, send_options = self._prepare_request(method, url, options)
        return await self.send(request, **send_options)

    async def send(self, request: httpx.Request, **options: Unpack[SendOptions]) -> httpx.Response:
        """Send an HTTP request asynchronously."""
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
        """Send a streaming HTTP request asynchronously using the httpx contract."""
        request, send_options = self._prepare_request(method, url, options)
        return self.stream_request(request, **send_options)

    def stream_request(
        self, request: httpx.Request, **options: Unpack[StreamOptions]
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Send a streaming HTTP request asynchronously.

        Return an asynchronous context manager for accessing the streaming response.

        Usage example:
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

        # Send the supplied Request: rebuilding it with client.stream()
        # broke streaming request bodies and passed a different object to hooks.
        response = await self.client.send(request, stream=True, auth=auth_to_use, follow_redirects=follow)
        try:
            yield response
        finally:
            await response.aclose()

    def _apply_decorators(self, func: AsyncSendMethod) -> AsyncSendMethod:
        """Apply all decorators to the function."""
        for decorator in self._config.send_decorators:
            func = cast("AsyncSendDecorator", decorator)(func)
        return func

    def _apply_stream_request_decorators(self, func: AsyncStreamRequestMethod) -> AsyncStreamRequestMethod:
        """Apply all stream_request decorators to the function."""
        for decorator in self._config.stream_decorators:
            func = cast("AsyncStreamRequestDecorator", decorator)(func)
        return func
