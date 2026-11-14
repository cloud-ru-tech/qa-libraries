"""http_client demo clients for local httpbin.

Run: docker compose up -d && uv run python -m examples.httpbin
"""

from .async_client import AsyncEchoApiClient, AsyncHttpbinClient, build_async_echo_client, build_async_httpbin_client
from .client import EchoApiClient, HttpbinClient, build_echo_client, build_httpbin_client
from .decorators import (
    TransportMetrics,
    async_metrics_decorator,
    async_stream_trace_decorator,
    metrics_decorator,
    stream_trace_decorator,
)
from .hooks import log_elapsed, stamp_started_at, warn_on_server_error, with_api_key
from .logging_setup import demo_logger, http_logger, setup_logging

__all__ = [
    "AsyncEchoApiClient",
    "AsyncHttpbinClient",
    "EchoApiClient",
    "HttpbinClient",
    "TransportMetrics",
    "async_metrics_decorator",
    "async_stream_trace_decorator",
    "build_async_echo_client",
    "build_async_httpbin_client",
    "build_echo_client",
    "build_httpbin_client",
    "demo_logger",
    "http_logger",
    "log_elapsed",
    "metrics_decorator",
    "setup_logging",
    "stamp_started_at",
    "stream_trace_decorator",
    "warn_on_server_error",
    "with_api_key",
]
