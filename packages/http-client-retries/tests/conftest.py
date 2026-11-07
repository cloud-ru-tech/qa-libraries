import logging
from collections.abc import Iterator
from dataclasses import replace

import pytest
from http_client_retries import config
from http_client_retries.config import Config
from http_client_retries.sleep_hooks import log_retry_error_hook
from tenacity import stop_after_attempt, wait_none

from tests.fakes import RecordingAsyncHook, RecordingHook

MAX_ATTEMPTS = 3


@pytest.fixture(autouse=True)
def reset_config_after_each_test() -> Iterator[None]:
    """Вернуть глобальную конфигурацию в исходное состояние после каждого теста.

    Сохраняется именно копия: configure() мутирует синглтон по месту, поэтому держать
    ссылку на него бесполезно.
    """
    original = replace(config.get_config())
    yield
    config.configure(options=original)


@pytest.fixture()
def fast_retries() -> None:
    """Короткая политика повторов без пауз."""
    config.configure(
        options=Config(stop=stop_after_attempt(MAX_ATTEMPTS), wait=wait_none(), before_sleep_hook=None, reraise=False),
    )


@pytest.fixture()
def reraising_retries() -> None:
    """Короткая политика повторов, возбуждающая исходную ошибку после последней попытки."""
    config.configure(
        options=Config(stop=stop_after_attempt(MAX_ATTEMPTS), wait=wait_none(), before_sleep_hook=None, reraise=True),
    )


@pytest.fixture()
def recorded_retries() -> RecordingHook:
    """Короткая политика повторов с хуком, запоминающим каждый повтор."""
    hook = RecordingHook()
    config.configure(
        options=Config(stop=stop_after_attempt(MAX_ATTEMPTS), wait=wait_none(), before_sleep_hook=hook, reraise=False),
    )
    return hook


@pytest.fixture()
def recorded_async_retries() -> RecordingAsyncHook:
    """То же, что recorded_retries, но с асинхронным хуком."""
    hook = RecordingAsyncHook()
    config.configure(
        options=Config(stop=stop_after_attempt(MAX_ATTEMPTS), wait=wait_none(), before_sleep_hook=hook, reraise=False),
    )
    return hook


@pytest.fixture()
def retry_logger() -> logging.Logger:
    logger = logging.getLogger("retry_test_logger")
    logger.setLevel(logging.ERROR)
    return logger


@pytest.fixture()
def logging_retries(retry_logger: logging.Logger) -> logging.Logger:
    """Короткая политика повторов, пишущая причину каждого повтора в лог."""
    config.configure(
        options=Config(
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=wait_none(),
            before_sleep_hook=log_retry_error_hook(retry_logger),
            reraise=False,
        ),
    )
    return retry_logger
