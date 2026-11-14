import logging
from collections.abc import Sequence
from uuid import uuid4

from httpx import Request, Response

from .config import LOGGING_CONFIG as CFG
from .types import RequestHook, ResponseHook
from .utils import logutils, traceparent

REQUEST_ID_HEADER = "X-Request-ID"
TRACEPARENT_HEADER = "Traceparent"

# Always mask these: leaking a single secret in logs is far worse
# than an unnecessary asterisk.
DEFAULT_SANITIZE_KEYS: tuple[str, ...] = (
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "api_key",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "token",
)


def request_logger_hook(
    logger: logging.Logger,
    sanitize_keys: Sequence[str],
    *,
    json_indent: int | None = None,
    use_line_breaks: bool | None = None,
    log_level: int | None = None,
) -> RequestHook:
    """Create a hook for safe HTTP request logging.

    :param logger: Log record recipient
    :param sanitize_keys: Fields to mask
    :param json_indent: JSON indentation
    :param use_line_breaks: Multiline formatting
    :param log_level: Log level
    :returns: Request hook
    """

    def log_request_hook(request: Request) -> None:
        log_msg = logutils.create_request_log(
            r=request,
            sanitize_keys=sanitize_keys,
            json_indent=_indent(json_indent),
            use_line_breaks=_line_breaks(use_line_breaks=use_line_breaks),
        )
        logger.log(level=_level(log_level), msg=log_msg)

    return log_request_hook


def response_logger_hook(
    logger: logging.Logger,
    sanitize_keys: Sequence[str],
    *,
    json_indent: int | None = None,
    use_line_breaks: bool | None = None,
    log_level: int | None = None,
) -> ResponseHook:
    """Create a hook for safe HTTP response logging.

    :param logger: Log record recipient
    :param sanitize_keys: Fields to mask
    :param json_indent: JSON indentation
    :param use_line_breaks: Multiline formatting
    :param log_level: Log level
    :returns: Response hook
    """

    def log_response_hook(response: Response) -> None:
        log_msg = logutils.create_response_log(
            r=response,
            sanitize_keys=sanitize_keys,
            json_indent=_indent(json_indent),
            use_line_breaks=_line_breaks(use_line_breaks=use_line_breaks),
        )
        logger.log(level=_level(log_level), msg=log_msg)

    return log_response_hook


def async_response_logger_hook(
    logger: logging.Logger,
    sanitize_keys: Sequence[str],
    *,
    json_indent: int | None = None,
    use_line_breaks: bool | None = None,
    log_level: int | None = None,
) -> ResponseHook:
    """Build a response logging hook for an asynchronous client.

    A separate implementation is needed: when the hook runs, the asynchronous
    response body has not been read and its stream is only accessible through await.
    """

    async def log_response_hook(response: Response) -> None:
        log_msg = await logutils.create_response_log_async(
            r=response,
            sanitize_keys=sanitize_keys,
            json_indent=_indent(json_indent),
            use_line_breaks=_line_breaks(use_line_breaks=use_line_breaks),
        )
        logger.log(level=_level(log_level), msg=log_msg)

    return log_response_hook


def request_id_hook(request: Request) -> None:
    """Set a request ID if it is missing.

    Preserve the existing value deliberately. The hook runs every time a request object
    is sent, and retries send the same object: overwriting the ID would give
    each attempt a new ID, preventing correlation in logs. For the same reason,
    preserve the ID supplied by the caller.
    """
    request.headers.setdefault(REQUEST_ID_HEADER, str(uuid4()))


def traceparent_hook(request: Request) -> None:
    """Set traceparent if it is missing. See :func:`request_id_hook` for details."""
    request.headers.setdefault(TRACEPARENT_HEADER, traceparent.generate())


def add_default_headers_hook(headers: dict[str, str]) -> RequestHook:
    """Create a hook to add missing request headers.

    :param headers: Default headers
    :returns: Request hook
    """
    defaults = dict(headers)

    def add_default_headers(request: Request) -> None:
        for name, value in defaults.items():
            if name not in request.headers:
                request.headers[name] = value

    return add_default_headers


def _level(log_level: int | None) -> int:
    return log_level if log_level is not None else CFG.log_level


def _indent(json_indent: int | None) -> int | None:
    return json_indent if json_indent is not None else CFG.json_indent


def _line_breaks(*, use_line_breaks: bool | None) -> bool:
    return use_line_breaks if use_line_breaks is not None else CFG.use_line_breaks
