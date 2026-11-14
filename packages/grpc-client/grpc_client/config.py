import logging
import os
from dataclasses import dataclass

# Default limit on logged message body length.
DEFAULT_PAYLOAD_LOG_MAXLENGTH = 4096

_TRUE_VALUES = ("true", "y", "yes", "on", "1")


@dataclass(kw_only=True)
class LoggingConfig:
    """gRPC request and response logging options."""

    # Request and response logging level.
    log_level: int = logging.INFO

    # Failed request logging level.
    err_log_level: int = logging.ERROR

    # Indentation width for formatting JSON properties.
    json_indent: int | None = None

    # Whether to put log properties on separate lines.
    use_line_breaks: bool = False

    # Maximum logged message body length. `None` means unlimited.
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
    """Configure logging options.

    Environment variable values take precedence over arguments.

    :param log_level: request and response logging level, defaults to INFO
    :param err_log_level: failed request logging level, defaults to ERROR
    :param json_indent: indentation width for JSON property formatting, defaults to no indentation
    :param use_line_breaks: whether to put log properties on separate lines, defaults to false
    :param payload_log_maxlength: maximum logged message body length, defaults to 4096 characters
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
