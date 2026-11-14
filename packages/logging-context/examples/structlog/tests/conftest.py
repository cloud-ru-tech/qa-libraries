from collections.abc import Iterator, Mapping, MutableMapping
from typing import Protocol, cast

import pytest
import structlog
from logging_context import LoggingContextHandler

from examples.structlog.shop import ShopClient


class _Processor(Protocol):
    def __call__(
        self, logger: object, method_name: str, event_dict: MutableMapping[str, object]
    ) -> Mapping[str, object] | str | bytes | bytearray | tuple[object, ...]: ...


class _FormatterType(Protocol):
    wrap_for_formatter: _Processor


structlog.configure(
    processors=[
        cast("_Processor", structlog.stdlib.add_logger_name),
        cast("_Processor", structlog.stdlib.add_log_level),
        cast("_FormatterType", structlog.stdlib.ProcessorFormatter).wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.stdlib.get_logger("tests")


def pytest_logging_context_configure(handler: LoggingContextHandler) -> None:
    """Set the log file format in this hook called once per run."""
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(ensure_ascii=False),
            foreign_pre_chain=[
                cast("_Processor", structlog.stdlib.add_logger_name),
                cast("_Processor", structlog.stdlib.add_log_level),
            ],
        ),
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    logger.info("прогон начинается", rootdir=str(session.config.rootpath))


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    logger.info("тестовое окружение магазина поднято")
    yield "https://shop.example"
    logger.info("тестовое окружение магазина погашено")


@pytest.fixture()
def shop(base_url: str) -> Iterator[ShopClient]:
    client = ShopClient(base_url)
    yield client
    client.clear_cart()
