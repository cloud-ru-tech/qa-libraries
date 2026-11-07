import codecs
import json
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import cast
from uuid import uuid4

from glom import GlomError
from httpx import Request, Response

from http_client.config import LOGGING_CONFIG as CFG

from .sanitizer import sanitize

ELLIPSIS = "..."
DEFAULT_ENCODING = "utf-8"

__all__ = [
    "create_request_log",
    "create_response_log",
    "create_response_log_async",
    "decode",
    "is_buffered",
    "is_streamed",
    "parse_error",
    "to_json",
    "trim",
]


def create_request_log(
    r: Request,
    sanitize_keys: Sequence[str],
    json_indent: int | None = None,
    *,
    use_line_breaks: bool = True,
) -> str:
    """Собрать лог HTTP-запроса.

    :param r: объект запроса с данными для логирования
    :param sanitize_keys: ключи в формате [glom](https://glom.readthedocs.io/en/latest/),
                          которые необходимо скрыть в данных запроса
    :param json_indent: ширина отступа для JSON свойств (по умолчанию отступ отсутствует)
    :param use_line_breaks: использовать ли переносы строк между свойствами запроса
    :returns: лог запроса
    """
    # NOTE: тут trace_id - это просто идентификатор, который связывает запрос с ответом.
    # Он не имеет ничего общего с trace_id от сервера, в котором включена телеметрия.
    trace_id = str(uuid4())
    extensions = cast("dict[str, object]", r.extensions)
    extensions["trace_id"] = trace_id

    log_parts = [
        f"Request: id={trace_id}",
        f"Method: [{r.method.upper()}] {r.url.scheme}://{r.url.host}{r.url.path}",
    ]

    _add_query_params(r, log_parts, sanitize_keys, json_indent)
    _add_headers(r, log_parts, sanitize_keys, json_indent)
    _add_body(r, log_parts, sanitize_keys, json_indent, streamed=not is_buffered(r))

    sep = _sep(use_line_breaks=use_line_breaks)
    return sep.join(log_parts)


def create_response_log(
    r: Response,
    sanitize_keys: Sequence[str],
    json_indent: int | None = None,
    *,
    use_line_breaks: bool = True,
) -> str:
    """Собрать лог ответа на HTTP-запрос.

    :param r: объект ответа на запрос с данными для логирования
    :param sanitize_keys: ключи в формате [glom](https://glom.readthedocs.io/en/latest/),
                          которые необходимо скрыть в данных ответа
    :param json_indent: ширина отступа для JSON свойств (по умолчанию отступ отсутствует)
    :param use_line_breaks: использовать ли переносы строк между свойствами запроса
    :returns: лог ответа на запрос
    """
    extensions = cast("dict[str, object]", r.request.extensions)
    trace_id = extensions.get("trace_id", "<none>")

    log_parts = [f"Response: id={trace_id}", f"Status: {r.status_code} [{r.reason_phrase}]"]

    _add_headers(r, log_parts, sanitize_keys, json_indent)
    _add_body(r, log_parts, sanitize_keys, json_indent, streamed=is_streamed(r))

    sep = _sep(use_line_breaks=use_line_breaks)
    return sep.join(log_parts)


async def create_response_log_async(
    r: Response,
    sanitize_keys: Sequence[str],
    json_indent: int | None = None,
    *,
    use_line_breaks: bool = True,
) -> str:
    """Собрать лог ответа асинхронного клиента.

    Response hook у httpx срабатывает до того, как клиент дочитал тело, поэтому
    у асинхронного ответа поток ещё асинхронный и синхронный read() к нему неприменим.

    :returns: лог ответа на запрос
    """
    await _aread_buffered(r)
    return create_response_log(r, sanitize_keys, json_indent, use_line_breaks=use_line_breaks)


async def _aread_buffered(r: Response) -> None:
    """Дочитать тело ответа, если оно не потоковое."""
    if is_streamed(r):
        return

    # Лог не должен ронять запрос: нечитаемое тело обработает _add_body.
    with suppress(Exception):
        await r.aread()


def _add_query_params(
    r: Request,
    log_parts: list[str],
    sanitize_keys: Sequence[str],
    json_indent: int | None,
) -> None:
    """Добавить query параметры в лог."""
    if not r.url.query:
        return

    try:
        sanitized_params = sanitize(dict(r.url.params.items()), sanitize_keys)
        log_parts.append(f"QueryParams: {to_json(sanitized_params, json_indent)}")
    except (TypeError, ValueError, GlomError) as e:
        log_parts.append(f"QueryParams: {parse_error(e)}")


def _add_headers(
    r: Request | Response,
    log_parts: list[str],
    sanitize_keys: Sequence[str],
    json_indent: int | None,
) -> None:
    """Добавить HTTP заголовки в лог."""
    try:
        sanitized_headers = sanitize(dict(r.headers.items()), sanitize_keys)
        log_parts.append(f"Headers: {to_json(sanitized_headers, json_indent)}")
    except (TypeError, ValueError, GlomError) as e:
        log_parts.append(f"Headers: {parse_error(e)}")


def _add_body(
    r: Request | Response,
    log_parts: list[str],
    sanitize_keys: Sequence[str],
    json_indent: int | None,
    *,
    streamed: bool,
) -> None:
    """Добавить тело запроса или ответа в лог."""
    if streamed:
        log_parts.append("Body: <streamed content>")
        return

    headers: Mapping[str, str] = r.headers
    content_type = headers.get("Content-Type", "").lower()
    try:
        if content_type.startswith("application/json"):
            decoded_body = cast("object", json.loads(r.read()))
            sanitized_body = sanitize(decoded_body, sanitize_keys)
            log_parts.append(f"Body: {trim(to_json(sanitized_body, json_indent), CFG.json_log_maxlength)}")
        elif content_type.startswith("text/plain"):
            log_parts.append(f"Body: {trim(decode(r), CFG.plain_text_log_maxlength)}")
        elif content_type.startswith("application/octet-stream"):
            log_parts.append(f"Body: {_octet_stream(r.read())}")
        elif content_type:
            log_parts.append(f"Body: <not logged, content-type: {content_type}>")
    except (TypeError, ValueError, GlomError, RuntimeError, OSError) as e:
        log_parts.append(f"Body: {parse_error(e)}")


def _octet_stream(content: bytes) -> str:
    try:
        return trim(content.decode(), CFG.octet_stream_log_maxlength)
    except UnicodeDecodeError:
        return f"<binary content ({len(content)} bytes)>"


def is_streamed(r: Response) -> bool:
    """Является ли ответ потоковым и ещё не вычитанным."""
    extensions = cast("dict[str, object]", r.request.extensions)
    return bool(extensions.get("is_streaming", False)) and not r.is_stream_consumed


def is_buffered(r: Request) -> bool:
    """Лежит ли тело запроса в памяти.

    У запроса с потоковым телом чтение израсходовало бы поток до отправки.
    """
    return hasattr(r, "_content")


def decode(r: Request | Response) -> str:
    """Декодировать тело с учётом charset из Content-Type."""
    content = r.read()
    headers: Mapping[str, str] = r.headers
    return content.decode(_charset(headers.get("Content-Type", "")), errors="replace")


def _charset(content_type: str) -> str:
    """Достать кодировку из Content-Type.

    У заголовка может быть несколько параметров (`text/plain; charset=utf-8; format=flowed`),
    поэтому charset выбирается по имени параметра, а не по остатку строки после `charset=`.
    Неизвестное имя кодировки не должно прятать тело, поэтому подменяется на utf-8.
    """
    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() != "charset":
            continue

        charset = value.strip().strip("\"'")
        if not charset:
            break

        try:
            codecs.lookup(charset)
        except LookupError:
            break

        return charset

    return DEFAULT_ENCODING


def parse_error(e: Exception) -> str:
    """Собрать безопасное описание ошибки разбора.

    Текст исключения не подставляется: он может содержать фрагменты тела или URL с секретами.
    """
    return f"<Error parse: {type(e).__name__}>"


def to_json(value: object, indent: int | None) -> str:
    """Сериализовать значение в JSON с сохранением Unicode.

    :param value: сериализуемое значение
    :param indent: ширина отступа
    :returns: JSON-представление
    """
    return json.dumps(value, indent=indent, ensure_ascii=False)


def trim(text: str, length: int | None) -> str:
    """Сократить строку, сохранив её начало и конец.

    :param text: исходная строка
    :param length: ограничение длины; None и неположительные числа отключают его
    :returns: исходная либо сокращённая строка
    """
    if not length or length < 0 or len(text) <= length:
        return text

    if length <= len(ELLIPSIS):
        return ELLIPSIS[:length]

    payload = length - len(ELLIPSIS)
    tail = payload // 2
    head = payload - tail
    return text[:head] + ELLIPSIS + (text[-tail:] if tail else "")


def _sep(*, use_line_breaks: bool) -> str:
    return "\n" if use_line_breaks else " "
