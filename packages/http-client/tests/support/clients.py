"""Фабрики HTTP-клиентов, закрывающих пул соединений после теста."""

from typing import Protocol

from http_client.client import AsyncHttpClient, ClientOption, HttpClient


class SyncClientFactory(Protocol):
    """Создать синхронный клиент, который будет закрыт после теста."""

    def __call__(
        self,
        base_url: str,
        *options: ClientOption,
        cls: type[HttpClient] = HttpClient,
    ) -> HttpClient: ...


class AsyncClientFactory(Protocol):
    """Создать асинхронный клиент, который будет закрыт после теста."""

    def __call__(
        self,
        base_url: str,
        *options: ClientOption,
        cls: type[AsyncHttpClient] = AsyncHttpClient,
    ) -> AsyncHttpClient: ...
