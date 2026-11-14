from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
from httpx._config import DEFAULT_MAX_REDIRECTS

if TYPE_CHECKING:
    import ssl

    from httpx._types import AuthTypes, TimeoutTypes, URLTypes

    from .types import RequestHook, ResponseHook, SendDecorator, StreamRequestDecorator

DEFAULT_OCTET_STREAM_LOG_MAXLENGTH = 1024


@dataclass(kw_only=True, slots=True)
class HttpClientConfig:
    """Transport settings collected by options before creating the HTTP client."""

    base_url: URLTypes
    verify: ssl.SSLContext | str | bool = True
    auth: AuthTypes | None = None
    timeout: TimeoutTypes = field(default_factory=lambda: httpx.Timeout(60))
    url_suffix: str = ""
    request_hooks: list[RequestHook] = field(default_factory=list)
    response_hooks: list[ResponseHook] = field(default_factory=list)
    send_decorators: list[SendDecorator] = field(default_factory=list)
    stream_decorators: list[StreamRequestDecorator] = field(default_factory=list)
    follow_redirects: bool = False
    max_redirects: int = DEFAULT_MAX_REDIRECTS


@dataclass(kw_only=True)
class LoggingConfig:
    """HTTP log formatting and length limit settings."""

    log_level: int = logging.INFO
    json_indent: int | None = None
    use_line_breaks: bool = False
    octet_stream_log_maxlength: int | None = DEFAULT_OCTET_STREAM_LOG_MAXLENGTH
    plain_text_log_maxlength: int | None = None
    json_log_maxlength: int | None = None


LOGGING_CONFIG = LoggingConfig()


def configure_logging(options: LoggingConfig | None = None) -> None:
    """Configure HTTP log formatting using environment variables.

    :param options: Default logging settings
    """
    settings = options or LoggingConfig()
    if log_level_env := os.getenv("HTTP_CLIENT_LOG_LEVEL", None):
        LOGGING_CONFIG.log_level = int(log_level_env)
    else:
        LOGGING_CONFIG.log_level = settings.log_level
    if use_line_breaks_env := os.getenv("HTTP_CLIENT_USE_LINE_BREAKS", None):
        LOGGING_CONFIG.use_line_breaks = use_line_breaks_env.lower() in ["true", "y", "yes", "on"]
    else:
        LOGGING_CONFIG.use_line_breaks = settings.use_line_breaks
    if json_indent_env := os.getenv("HTTP_CLIENT_JSON_INDENT", None):
        LOGGING_CONFIG.json_indent = int(json_indent_env)
    else:
        LOGGING_CONFIG.json_indent = settings.json_indent
    if octet_stream_log_maxlength_env := os.getenv("HTTP_CLIENT_OCTET_STREAM_LOG_MAXLENGTH", None):
        LOGGING_CONFIG.octet_stream_log_maxlength = int(octet_stream_log_maxlength_env)
    else:
        LOGGING_CONFIG.octet_stream_log_maxlength = settings.octet_stream_log_maxlength
    if plain_text_log_maxlength_env := os.getenv("HTTP_CLIENT_PLAIN_TEXT_LOG_MAXLENGTH", None):
        LOGGING_CONFIG.plain_text_log_maxlength = int(plain_text_log_maxlength_env)
    else:
        LOGGING_CONFIG.plain_text_log_maxlength = settings.plain_text_log_maxlength
    if json_log_maxlength_env := os.getenv("HTTP_CLIENT_JSON_LOG_MAXLENGTH", None):
        LOGGING_CONFIG.json_log_maxlength = int(json_log_maxlength_env)
    else:
        LOGGING_CONFIG.json_log_maxlength = settings.json_log_maxlength
