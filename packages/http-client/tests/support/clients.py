"""HTTP client factories that close connection pools after the test."""

from typing import Protocol

from http_client.client import AsyncHttpClient, ClientOption, HttpClient


class SyncClientFactory(Protocol):
    """Create a synchronous client that will be closed after the test."""

    def __call__(
        self,
        base_url: str,
        *options: ClientOption,
        cls: type[HttpClient] = HttpClient,
    ) -> HttpClient: ...


class AsyncClientFactory(Protocol):
    """Create an asynchronous client that will be closed after the test."""

    def __call__(
        self,
        base_url: str,
        *options: ClientOption,
        cls: type[AsyncHttpClient] = AsyncHttpClient,
    ) -> AsyncHttpClient: ...
