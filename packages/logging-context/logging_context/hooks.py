from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

    from .handler import LoggingContextHandler


def pytest_logging_context_configure(
    handler: LoggingContextHandler,
    config: pytest.Config,
) -> None:
    """Configure the log handler before the run starts.

    Called once after the plugin creates the handler and attaches it to
    loggers. Extension point for formatters that cannot be expressed as an
    ini, such as `structlog.stdlib.ProcessorFormatter` or JSON formatting.

    :param handler: handler that writes logs to test files
    :param config: pytest configuration
    """
