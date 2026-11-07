import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import cast

import pytest
from http_client import config
from http_client.client import AsyncHttpClient, ClientOption, HttpClient

from .support.clients import AsyncClientFactory, SyncClientFactory
from .support.logs import RecordedLog, RecordingHandler


@pytest.fixture(autouse=True)
def restore_logging_config() -> Iterator[None]:
    """Вернуть глобальную конфигурацию логирования после теста.

    LOGGING_CONFIG — модульный синглтон, поэтому без восстановления настройки
    одного теста меняют поведение всех последующих.
    """
    snapshot = cast("dict[str, object]", vars(replace(config.LOGGING_CONFIG)))
    yield
    for field, value in snapshot.items():
        setattr(config.LOGGING_CONFIG, field, value)


@pytest.fixture()
def new_client() -> Iterator[SyncClientFactory]:
    """Фабрика синхронных клиентов, закрывающая их пулы соединений после теста."""
    created: list[HttpClient] = []

    def factory(base_url: str, *options: ClientOption, cls: type[HttpClient] = HttpClient) -> HttpClient:
        client = cls(base_url, *options)
        created.append(client)
        return client

    yield factory

    for client in created:
        client.close()


@pytest.fixture()
async def new_async_client() -> AsyncIterator[AsyncClientFactory]:
    """Фабрика асинхронных клиентов, закрывающая их пулы соединений после теста."""
    created: list[AsyncHttpClient] = []

    def factory(
        base_url: str,
        *options: ClientOption,
        cls: type[AsyncHttpClient] = AsyncHttpClient,
    ) -> AsyncHttpClient:
        client = cls(base_url, *options)
        created.append(client)
        return client

    yield factory

    for client in created:
        await client.aclose()


@pytest.fixture()
def recorded_log(request: pytest.FixtureRequest) -> Iterator[RecordedLog]:
    """Настоящий логгер с перехватом записей — фейк вместо мока.

    У каждого теста собственный логгер, поэтому записи не утекают между тестами.
    """
    logger = logging.getLogger(f"http_client.tests.{cast('pytest.Item', request.node).nodeid}")
    handler = RecordingHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    yield RecordedLog(logger=logger, handler=handler)

    logger.removeHandler(handler)
