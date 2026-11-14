"""Asynchronous demo client for local httpbin.

Differs from the synchronous client in two ways: its base class and await.
Options are the same, including synchronous hooks, which the client wraps in coroutines.
The exception is send/stream_request decorators: for the asynchronous client they must
be asynchronous.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from http_client import AsyncHttpClient, options
from httpx import BasicAuth, Timeout

from . import settings
from .decorators import async_metrics_decorator, async_stream_trace_decorator
from .hooks import log_elapsed, stamp_started_at, warn_on_server_error, with_api_key
from .logging_setup import demo_logger, http_logger

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    import httpx

    from .decorators import TransportMetrics


class AsyncHttpbinClient(AsyncHttpClient):
    """Asynchronous client for httpbin."""

    async def get_echo(self, **params: str) -> httpx.Response:
        """GET /get: echo the query string."""
        request = self.client.build_request("GET", "/get", params=params)
        return await self.send(request)

    async def post_json(self, payload: object) -> httpx.Response:
        """POST /post: echo the request body."""
        request = self.client.build_request("POST", "/post", json=payload)
        return await self.send(request)

    async def put_json(self, payload: object) -> httpx.Response:
        """PUT /put: echo the request body."""
        request = self.client.build_request("PUT", "/put", json=payload)
        return await self.send(request)

    async def patch_json(self, payload: object) -> httpx.Response:
        """PATCH /patch: echo the request body."""
        request = self.client.build_request("PATCH", "/patch", json=payload)
        return await self.send(request)

    async def delete_resource(self) -> httpx.Response:
        """DELETE /delete."""
        request = self.client.build_request("DELETE", "/delete")
        return await self.send(request)

    async def get_request_headers(self) -> httpx.Response:
        """GET /headers: headers received by the service from the client."""
        request = self.client.build_request("GET", "/headers")
        return await self.send(request)

    async def basic_auth(self, user: str, password: str, *, anonymous: bool = False) -> httpx.Response:
        """GET /basic-auth/{user}/{password}: check Basic authentication.

        :param user: Username expected by the service
        :param password: Password expected by the service
        :param anonymous: Disable client authentication entirely
        """
        request = self.client.build_request("GET", f"/basic-auth/{user}/{password}")
        return await self.send(request, anonymous=anonymous)

    async def delay(self, seconds: float, *, timeout_seconds: float) -> httpx.Response:
        """GET /delay/{seconds}: delayed response.

        :param seconds: Service-side delay
        :param timeout_seconds: Timeout for this call; overrides the client timeout
        """
        request = self.client.build_request("GET", f"/delay/{seconds}", timeout=timeout_seconds)
        return await self.send(request)

    async def redirect(self, times: int, *, follow_redirects: bool | None = None) -> httpx.Response:
        """GET /redirect/{times}: redirect chain ending at /get.

        :param times: Chain length
        :param follow_redirects: Override redirect following for this call
        """
        request = self.client.build_request("GET", f"/redirect/{times}")
        return await self.send(request, follow_redirects=follow_redirects)

    async def status(self, code: int) -> httpx.Response:
        """GET /status/{code}: response with the specified status."""
        request = self.client.build_request("GET", f"/status/{code}")
        return await self.send(request)

    async def get_bytes(self, size: int) -> httpx.Response:
        """GET /bytes/{size}: random bytes in one chunk (application/octet-stream)."""
        request = self.client.build_request("GET", f"/bytes/{size}")
        return await self.send(request)

    def stream_lines(self, count: int) -> AbstractAsyncContextManager[httpx.Response]:
        """GET /stream/{count}: stream of JSON lines.

        The method is not a coroutine: it returns an asynchronous context manager,
        so call it with `async with`, without await.
        """
        request = self.client.build_request("GET", f"/stream/{count}")
        return self.stream_request(request)

    def stream_bytes(self, size: int) -> AbstractAsyncContextManager[httpx.Response]:
        """GET /stream-bytes/{size}: stream of random bytes (application/octet-stream)."""
        request = self.client.build_request("GET", f"/stream-bytes/{size}")
        return self.stream_request(request)


class AsyncEchoApiClient(AsyncHttpClient):
    """Asynchronous client with a path prefix."""

    DEFAULT_URL_SUFFIX = "/anything/api/v1"

    async def ping(self) -> httpx.Response:
        """GET {suffix}/ping."""
        request = self.client.build_request("GET", self.endpoint("ping"))
        return await self.send(request)


def build_async_httpbin_client(metrics: TransportMetrics) -> AsyncHttpbinClient:
    """Build an asynchronous client with all options.

    Options match the synchronous client except for transport decorators.

    :param metrics: Counters for the send decorator
    :returns: Client ready for use
    """
    return AsyncHttpbinClient(
        settings.BASE_URL,
        options.with_timeout(Timeout(connect=2.0, read=5.0, write=5.0, pool=1.0)),
        options.with_auth(BasicAuth(settings.DEMO_USER, settings.DEMO_PASSWORD)),
        options.with_default_headers(
            {
                "X-Client-Name": settings.CLIENT_NAME,
                "X-Client-Version": settings.CLIENT_VERSION,
            }
        ),
        with_api_key(settings.DEMO_API_KEY),
        options.with_autogenerated_request_id(),
        options.with_autogenerated_traceparent(),
        options.with_request_hook(stamp_started_at),
        options.with_logger(http_logger(), sanitize_keys=settings.SANITIZE_KEYS),
        options.with_response_hook(log_elapsed(demo_logger())),
        options.with_response_hook(warn_on_server_error(demo_logger())),
        options.with_send_decorator(async_metrics_decorator(metrics, demo_logger())),
        options.with_stream_decorator(async_stream_trace_decorator(demo_logger())),
    )


def build_async_echo_client() -> AsyncEchoApiClient:
    """Build an asynchronous client with a path prefix and minimal options."""
    return AsyncEchoApiClient(
        settings.BASE_URL,
        options.with_timeout(5),
        options.with_logger(http_logger()),
    )
