"""Request and response hooks plus a custom client option.

These hooks are synchronous and used by both clients: AsyncHttpClient
wraps synchronous hooks in coroutines in its __init__.
"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from logging import Logger

    import httpx
    from http_client import ClientOption
    from http_client.client import BaseHttpClient
    from http_client.types import ResponseHook

API_KEY_HEADER = "X-Api-Key"
STARTED_AT_EXTENSION = "demo_started_at"


def stamp_started_at(request: httpx.Request) -> None:
    """Store the send timestamp in the request extensions.

    extensions is the only place that survives until the response hook:
    log_elapsed reads it there through response.request.
    """
    cast("dict[str, object]", request.extensions)[STARTED_AT_EXTENSION] = perf_counter()


def log_elapsed(logger: Logger) -> ResponseHook:
    """Build a response hook that logs request duration.

    :param logger: Logger for duration records
    :returns: Response hook paired with stamp_started_at
    """

    def log_elapsed_hook(response: httpx.Response) -> None:
        started_at = cast("dict[str, object]", response.request.extensions).get(STARTED_AT_EXTENSION)
        if not isinstance(started_at, float):
            return

        elapsed_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "Длительность: %s %s -> %s за %.1f мс",
            response.request.method,
            response.request.url.path,
            response.status_code,
            elapsed_ms,
        )

    return log_elapsed_hook


def warn_on_server_error(logger: Logger) -> ResponseHook:
    """Build a response hook that warns on 5xx statuses.

    The hook does not read the response body: streaming responses have not loaded it yet,
    and reading it in the hook would break streaming.

    :param logger: Logger for warnings
    :returns: Response hook
    """

    def warn_on_server_error_hook(response: httpx.Response) -> None:
        if response.is_server_error:
            logger.warning(
                "Сервер вернул %s на %s %s",
                response.status_code,
                response.request.method,
                response.request.url.path,
            )

    return warn_on_server_error_hook


def with_api_key(api_key: str) -> ClientOption:
    """Build an option that adds the X-Api-Key header to every request.

    Prepend the hook so the header appears in logs regardless of
    the order of constructor options: with_logger appends its hook.
    Build options that do not need a specific list position using with_request_hook.

    :param api_key: Header value
    :returns: Client option
    """

    def add_api_key(request: httpx.Request) -> None:
        request.headers[API_KEY_HEADER] = api_key

    def option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_api_key, prepend=True)

    return option
