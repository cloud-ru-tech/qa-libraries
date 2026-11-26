import logging
from collections.abc import Iterator
from contextlib import contextmanager
from threading import get_ident

import httpx2

logger = logging.getLogger(__name__)


def post_notification(
    destination: str,
    url: str,
    payload: dict[str, object],
    timeout: float,
    *,
    bot_token: str | None = None,
) -> None:
    """Post a notification and report only the destination and delivery outcome.

    :param destination: Public channel name for diagnostics.
    :param url: Credential-bearing delivery URL.
    :param payload: JSON message.
    :param timeout: HTTP timeout in seconds.
    :param bot_token: Telegram credential embedded inside a URL path segment.
    :raises RuntimeError: If the request fails or the server returns a non-success status.
    """
    try:
        endpoint = httpx2.URL(url)
        client = httpx2.Client(timeout=timeout)
        with _hide_delivery_logs(endpoint, bot_token), client:
            response = client.post(endpoint, json=payload)
    except (httpx2.HTTPError, httpx2.InvalidURL) as exc:
        outcome = type(exc).__name__
    else:
        outcome = f"HTTP {response.status_code}"
        if response.is_success:
            logger.info("%s: %s", destination, outcome)
            return

    message = f"{destination}: {outcome}"
    logger.warning(message)
    raise RuntimeError(message)


@contextmanager
def _hide_delivery_logs(endpoint: httpx2.URL, bot_token: str | None) -> Iterator[None]:
    # HTTPX logs the URL; httpcore debug logs can also contain server-supplied headers.
    sender = get_ident()
    secrets = {str(endpoint), endpoint.username, endpoint.password, *endpoint.params.values()}
    if bot_token is not None:
        secrets.add(bot_token)
    else:
        raw_path = endpoint.raw_path.decode("ascii").partition("?")[0]
        for path in (endpoint.path, raw_path):
            secrets.add(path.rstrip("/").rsplit("/", 1)[-1])
    secrets.discard("")

    def keep_unrelated(record: logging.LogRecord) -> bool:
        if get_ident() != sender:
            return True
        message = record.getMessage()
        return not any(secret in message for secret in secrets)

    loggers = [
        item
        for name, item in logging.Logger.manager.loggerDict.copy().items()
        if name.partition(".")[0] in {"httpx2", "httpcore2"} and isinstance(item, logging.Logger)
    ]
    for transport_logger in loggers:
        transport_logger.addFilter(keep_unrelated)
    try:
        yield
    finally:
        for transport_logger in loggers:
            transport_logger.removeFilter(keep_unrelated)
