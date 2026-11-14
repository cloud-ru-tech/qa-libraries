"""Logging setup for httpbin demo clients."""

import logging
import sys

from http_client import configure_logging
from http_client.config import LoggingConfig

HTTP_LOGGER_NAME = "httpbin.http"
DEMO_LOGGER_NAME = "httpbin.demo"

_LOG_FORMAT = "%(levelname)-7s %(name)-12s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Set up console output and global http_client log settings.

    configure_logging sets defaults for all clients in the process:
    any with_logger option without an explicit argument reads them here.
    HTTP_CLIENT_* environment variables override these arguments.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)

    # httpx logging would duplicate the request line alongside the detailed http_client log
    logging.getLogger("httpx").setLevel(logging.WARNING)

    configure_logging(
        options=LoggingConfig(log_level=level, json_indent=2, use_line_breaks=True, octet_stream_log_maxlength=128)
    )


def http_logger() -> logging.Logger:
    """Logger that receives http_client requests and responses."""
    return logging.getLogger(HTTP_LOGGER_NAME)


def demo_logger() -> logging.Logger:
    """Logger for explanations of demo scenarios."""
    return logging.getLogger(DEMO_LOGGER_NAME)
