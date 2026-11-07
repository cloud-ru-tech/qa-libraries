"""Настройка логирования для демо-клиентов httpbin."""

import logging
import sys

from http_client import configure_logging
from http_client.config import LoggingConfig

HTTP_LOGGER_NAME = "httpbin.http"
DEMO_LOGGER_NAME = "httpbin.demo"

_LOG_FORMAT = "%(levelname)-7s %(name)-12s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Поднять вывод в консоль и глобальные настройки логов http_client.

    configure_logging задаёт значения по умолчанию для всех клиентов процесса:
    любая опция with_logger, которой не передали аргумент, читает их отсюда.
    Переменные окружения HTTP_CLIENT_* перекрывают эти аргументы.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)

    # Свой лог httpx дублировал бы строку запроса рядом с подробным логом http_client
    logging.getLogger("httpx").setLevel(logging.WARNING)

    configure_logging(
        options=LoggingConfig(log_level=level, json_indent=2, use_line_breaks=True, octet_stream_log_maxlength=128)
    )


def http_logger() -> logging.Logger:
    """Логгер, в который http_client пишет запросы и ответы."""
    return logging.getLogger(HTTP_LOGGER_NAME)


def demo_logger() -> logging.Logger:
    """Логгер для пояснений к сценариям демо."""
    return logging.getLogger(DEMO_LOGGER_NAME)
