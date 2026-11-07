import logging
import os
from dataclasses import dataclass

# Ограничение на длину тела сообщения в логе по умолчанию.
DEFAULT_PAYLOAD_LOG_MAXLENGTH = 4096

_TRUE_VALUES = ("true", "y", "yes", "on", "1")


@dataclass(kw_only=True)
class LoggingConfig:
    """Параметры логирования gRPC-запросов и ответов."""

    # Уровень логирования запросов и ответов.
    log_level: int = logging.INFO

    # Уровень логирования запросов, завершившихся ошибкой.
    err_log_level: int = logging.ERROR

    # Ширина отступа при форматировании JSON свойств.
    json_indent: int | None = None

    # Разносить ли свойства лога по строкам.
    use_line_breaks: bool = False

    # Максимальная длина тела сообщения в логе. `None` — без ограничения.
    payload_log_maxlength: int | None = DEFAULT_PAYLOAD_LOG_MAXLENGTH


LOGGING_CONFIG = LoggingConfig()


def configure_logging(
    *,
    log_level: int = logging.INFO,
    err_log_level: int = logging.ERROR,
    json_indent: int | None = None,
    use_line_breaks: bool = False,
    payload_log_maxlength: int | None = DEFAULT_PAYLOAD_LOG_MAXLENGTH,
) -> None:
    """Сконфигурировать параметры логирования.

    Значения из переменных окружения имеют приоритет над аргументами.

    :param log_level: уровень логирования запросов и ответов, по умолчанию INFO
    :param err_log_level: уровень логирования запросов с ошибкой, по умолчанию ERROR
    :param json_indent: ширина отступа при форматировании JSON свойств, по умолчанию отступа нет
    :param use_line_breaks: разносить ли свойства лога по строкам, по умолчанию нет
    :param payload_log_maxlength: максимальная длина тела сообщения в логе, по умолчанию 4096 символов
    """
    LOGGING_CONFIG.log_level = _env_int("GRPC_CLIENT_LOG_LEVEL", log_level)
    LOGGING_CONFIG.err_log_level = _env_int("GRPC_CLIENT_ERR_LOG_LEVEL", err_log_level)
    LOGGING_CONFIG.json_indent = _env_optional_int("GRPC_CLIENT_JSON_INDENT", json_indent)
    LOGGING_CONFIG.use_line_breaks = _env_bool("GRPC_CLIENT_USE_LINE_BREAKS", default=use_line_breaks)
    LOGGING_CONFIG.payload_log_maxlength = _env_optional_int(
        "GRPC_CLIENT_PAYLOAD_LOG_MAXLENGTH",
        payload_log_maxlength,
    )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _env_optional_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    return int(value) if value else default


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    return value.lower() in _TRUE_VALUES if value else default
