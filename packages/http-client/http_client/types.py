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
    """Named logging settings for an individual HTTP client."""

    sanitize_keys: Sequence[str] | None
    json_indent: int | None
    use_line_breaks: bool | None
    log_level: int | None
    use_default_sanitize_keys: bool


class QueryOptions(TypedDict, total=False):
    """Named options for an HTTP request without a body."""

    params: QueryParamTypes | None
    headers: HeaderTypes | None
    cookies: CookieTypes | None
    auth: AuthTypes | None
    follow_redirects: bool | None
    timeout: TimeoutTypes | UseClientDefault
    extensions: dict[str, object] | None
    anonymous: bool


class RequestOptions(QueryOptions, total=False):
    """Named options for an HTTP request with a body."""

    content: RequestContent | None
    data: RequestData | None
    files: RequestFiles | None
    json: object


class StreamOptions(TypedDict, total=False):
    """Options for sending a prepared request in streaming mode."""

    auth: AuthTypes | None
    follow_redirects: bool | None
    anonymous: bool


class SendOptions(StreamOptions, total=False):
    """Options for sending a prepared HTTP request."""

    stream: bool


class SyncSendMethod(Protocol):
    """Protocol for a synchronous send method."""

    def __call__(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        """Send a prepared HTTP request and return the response."""
        ...


class AsyncSendMethod(Protocol):
    """Protocol for an asynchronous send method."""

    async def __call__(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
        anonymous: bool = False,
    ) -> httpx.Response:
        """Send a prepared HTTP request asynchronously and return the response."""
        ...


class SyncStreamRequestMethod(Protocol):
    """Protocol for a synchronous stream_request method."""

    def __call__(
        self,
        request: httpx.Request,
        *,
        anonymous: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
    ) -> AbstractContextManager[httpx.Response]:
        """Open a streaming HTTP response context."""
        ...


class AsyncStreamRequestMethod(Protocol):
    """Protocol for an asynchronous stream_request method."""

    def __call__(
        self,
        request: httpx.Request,
        *,
        anonymous: bool = False,
        auth: AuthTypes | None = None,
        follow_redirects: bool | None = None,
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Open an asynchronous streaming HTTP response context."""
        ...


# Types for send method decorators
SyncSendDecorator = Callable[[SyncSendMethod], SyncSendMethod]
AsyncSendDecorator = Callable[[AsyncSendMethod], AsyncSendMethod]

SendDecorator = SyncSendDecorator | AsyncSendDecorator

# Types for stream_request method decorators
SyncStreamRequestDecorator = Callable[[SyncStreamRequestMethod], SyncStreamRequestMethod]
AsyncStreamRequestDecorator = Callable[[AsyncStreamRequestMethod], AsyncStreamRequestMethod]

StreamRequestDecorator = SyncStreamRequestDecorator | AsyncStreamRequestDecorator
