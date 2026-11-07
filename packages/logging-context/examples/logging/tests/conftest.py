import logging
from collections.abc import Iterator

import pytest

from examples.logging.shop import ShopClient

logger = logging.getLogger("tests")


def pytest_sessionstart(session: pytest.Session) -> None:
    logger.info("прогон начинается, rootdir=%s", session.config.rootpath)


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    logger.info("поднимаем тестовое окружение магазина")
    yield "https://shop.example"
    logger.info("гасим тестовое окружение магазина")


@pytest.fixture()
def shop(base_url: str) -> Iterator[ShopClient]:
    client = ShopClient(base_url)
    yield client
    client.clear_cart()
