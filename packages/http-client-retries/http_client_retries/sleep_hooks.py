import logging
from collections.abc import Callable
from typing import cast

from httpx import Request
from tenacity import RetryCallState

from ._types import is_http_request, is_http_response


def log_retry_error_hook(logger: logging.Logger) -> Callable[[RetryCallState], None]:
    """Prepare a sleep_hook to log the error when retrying a request."""

    def before_sleep_hook(retry_state: RetryCallState) -> None:
        request = _extract_request(retry_state)
        err_name, err_description = _prepare_retry_error_context(retry_state)

        if request is None:
            logger.error("Failed http request: %s: %s", err_name, err_description)
            return

        logger.error(
            "Failed http request [%s] %s://%s%s with id=%s: %s: %s",
            request.method,
            request.url.scheme,
            request.url.host,
            request.url.path,
            cast("dict[str, object]", request.extensions).get("trace_id", "<none>"),
            err_name,
            err_description,
        )

    return before_sleep_hook


def _extract_request(retry_state: RetryCallState) -> Request | None:
    """Find the request in positional or keyword call arguments."""
    for candidate in (
        *cast("tuple[object, ...]", retry_state.args),
        cast("dict[str, object]", retry_state.kwargs).get("request"),
    ):
        if is_http_request(candidate):
            return candidate

    return None


def _prepare_retry_error_context(retry_state: RetryCallState) -> tuple[str, str]:
    """Extract error information from an attempt result."""
    outcome = retry_state.outcome
    if outcome is None:
        return "UnknownError", "result = None"

    if outcome.failed:
        error = outcome.exception()
        return type(error).__name__, str(error)

    result = cast("object", outcome.result())
    if is_http_response(result):
        return "ServiceUnavailable", f"status code = {result.status_code}"

    return "UnknownError", f"result = {result}"
