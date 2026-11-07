from collections.abc import AsyncIterator, Iterator

import pytest

from .client import AsyncExampleClient, ExampleClient
from .endpoints import BASE_API_URL


@pytest.fixture()
def client() -> Iterator[ExampleClient]:
    with ExampleClient(base_url=BASE_API_URL) as client:
        yield client


@pytest.fixture()
async def async_client() -> AsyncIterator[AsyncExampleClient]:
    async with AsyncExampleClient(base_url=BASE_API_URL) as client:
        yield client
