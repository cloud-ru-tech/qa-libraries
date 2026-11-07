from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

    from .handler import LoggingContextHandler


def pytest_logging_context_configure(
    handler: LoggingContextHandler,
    config: pytest.Config,
) -> None:
    """Настроить хендлер логов до начала прогона.

    Вызывается один раз после того, как плагин создал хендлер и повесил его на
    логгеры. Точка расширения для форматтеров, которые нельзя описать строкой в
    ini — например `structlog.stdlib.ProcessorFormatter` или JSON-формат.

    :param handler: хендлер, который пишет логи в файлы тестов
    :param config: конфигурация pytest
    """
