import logging
from collections.abc import Sequence
from uuid import uuid4

from httpx import Request, Response

from .config import LOGGING_CONFIG as CFG
from .types import RequestHook, ResponseHook
from .utils import logutils, traceparent

REQUEST_ID_HEADER = "X-Request-ID"
TRACEPARENT_HEADER = "Traceparent"

# Маскируется всегда: цена одного пропущенного секрета в логах несопоставима
# с неудобством от лишней звёздочки.
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
    """Создать хук безопасного логирования HTTP-запроса.

    :param logger: получатель записей
    :param sanitize_keys: скрываемые поля
    :param json_indent: отступ JSON
    :param use_line_breaks: форматирование нескольких строк
    :param log_level: уровень записей
    :returns: хук запроса
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
    """Создать хук безопасного логирования HTTP-ответа.

    :param logger: получатель записей
    :param sanitize_keys: скрываемые поля
    :param json_indent: отступ JSON
    :param use_line_breaks: форматирование нескольких строк
    :param log_level: уровень записей
    :returns: хук ответа
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
    """Собрать хук логирования ответа для асинхронного клиента.

    Нужна отдельная реализация: на момент срабатывания хука тело асинхронного
    ответа ещё не прочитано, а его поток доступен только через await.
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
    """Проставить идентификатор запроса, если его ещё нет.

    Существующее значение намеренно не перезаписывается. Хук срабатывает на каждой отправке
    объекта запроса, а повторная попытка отправляет тот же объект: перезапись выдавала бы
    каждой попытке новый идентификатор, и связать их в логах было бы нельзя. По той же причине
    сохраняется идентификатор, который проставил вызывающий код.
    """
    request.headers.setdefault(REQUEST_ID_HEADER, str(uuid4()))


def traceparent_hook(request: Request) -> None:
    """Проставить traceparent, если его ещё нет. Подробности — в :func:`request_id_hook`."""
    request.headers.setdefault(TRACEPARENT_HEADER, traceparent.generate())


def add_default_headers_hook(headers: dict[str, str]) -> RequestHook:
    """Создать хук добавления отсутствующих заголовков запроса.

    :param headers: заголовки по умолчанию
    :returns: хук запроса
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
