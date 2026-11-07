from collections.abc import Iterator

import pytest
from explicit_wait import reset_config

from .fakes import FakeClock


@pytest.fixture(autouse=True)
def reset_global_config() -> Iterator[None]:
    reset_config()
    yield
    reset_config()


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()
