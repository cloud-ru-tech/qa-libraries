import httpx
from http_client.config import LOGGING_CONFIG as CFG
from http_client.types import RequestHook, ResponseHook
from structlog.stdlib import BoundLogger

from .parser import parse_request, parse_response, parse_response_async
from .sanitizer import Sanitizer

REQUEST_EVENT = "http request sent"
RESPONSE_EVENT = "http response received"


def request_logger_hook(
    logger: BoundLogger,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
    log_level: int | None = None,
) -> RequestHook:
    """Build a structured HTTP request logging hook."""

    def log_request_hook(request: httpx.Request) -> None:
        request_params = parse_request(
            request=request,
            sanitizer=sanitizer,
            json_indent=_indent(json_indent),
        )
        logger.log(_level(log_level), REQUEST_EVENT, **request_params)

    return log_request_hook


def response_logger_hook(
    logger: BoundLogger,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
    log_level: int | None = None,
) -> ResponseHook:
    """Build a structured HTTP response logging hook."""

    def log_response_hook(response: httpx.Response) -> None:
        response_params = parse_response(
            response=response,
            sanitizer=sanitizer,
            json_indent=_indent(json_indent),
        )
        logger.log(_level(log_level), RESPONSE_EVENT, **response_params)

    return log_response_hook


def async_response_logger_hook(
    logger: BoundLogger,
    sanitizer: Sanitizer,
    json_indent: int | None = None,
    log_level: int | None = None,
) -> ResponseHook:
    """Build a response logging hook for an asynchronous client.

    A separate implementation is needed: when the hook runs, the asynchronous
    response body has not been read and its stream is only accessible through await.
    """

    async def log_response_hook(response: httpx.Response) -> None:
        response_params = await parse_response_async(
            response=response,
            sanitizer=sanitizer,
            json_indent=_indent(json_indent),
        )
        logger.log(_level(log_level), RESPONSE_EVENT, **response_params)

    return log_response_hook


def _level(log_level: int | None) -> int:
    return log_level if log_level is not None else CFG.log_level


def _indent(json_indent: int | None) -> int | None:
    return json_indent if json_indent is not None else CFG.json_indent
