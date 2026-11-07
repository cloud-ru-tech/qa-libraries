import json
from collections.abc import Sequence
from typing import cast
from urllib.parse import urlencode

import httpx
from http_client.utils import sanitizer

STREAMED_CONTENT = "<streamed content>"

JSON_CONTENT_TYPE = "application/json"


def decode(body: bytes) -> str:
    """Декодировать тело запроса или ответа, не падая на бинарных данных."""
    try:
        return body.decode()
    except UnicodeDecodeError:
        return f"<binary data {len(body)} bytes>"


class Unparsed:
    """Признак того, что тело не удалось разобрать как JSON.

    Отдельный тип, а не None или str: разобранным значением может быть и то, и другое.
    """


UNPARSED = Unparsed()


def parse_json_body(text: str, sanitize_keys: Sequence[str]) -> object:
    """Разобрать JSON тело и замаскировать в нем секреты.

    :param text: текстовое представление тела
    :param sanitize_keys: ключи в формате glom для маскирования секретов
    :return: разобранное значение либо UNPARSED, если тело не является JSON
    """
    try:
        parsed = cast("object", json.loads(text))
    except json.JSONDecodeError:
        return UNPARSED

    # Ветки раздельные: у sanitize TypeVar ограничен значениями dict и list, объединение он не примет.
    if isinstance(parsed, dict):
        return sanitizer.sanitize(cast("dict[str, object]", parsed), sanitize_keys)

    if isinstance(parsed, list):
        return sanitizer.sanitize(cast("list[object]", parsed), sanitize_keys)

    return parsed


def render_body(
    body: bytes | None,
    content_type: str,
    sanitize_keys: Sequence[str],
) -> object:
    """Подготовить тело к сериализации во вложение.

    :param body: тело запроса или ответа, None означает непрочитанный поток
    :param content_type: значение заголовка Content-Type
    :param sanitize_keys: ключи в формате glom для маскирования секретов
    :return: разобранный и замаскированный JSON либо текстовое представление тела
    """
    if body is None:
        return STREAMED_CONTENT

    text = decode(body)
    if not content_type.startswith(JSON_CONTENT_TYPE):
        return text

    parsed = parse_json_body(text, sanitize_keys)

    # Заголовок обещал JSON, но тело им не является - показываем как есть,
    # ломать запрос из-за оформления отчета нельзя.
    return text if parsed is UNPARSED else parsed


QueryParams = dict[str, str | list[str]]


def sanitize_query_params(request: httpx.Request, sanitize_keys: Sequence[str]) -> QueryParams:
    """Вернуть query параметры запроса с замаскированными секретами.

    Повторяющиеся ключи собираются в список, иначе отчет расходился бы с тем,
    что реально ушло на сервер: из `tag=a&tag=b` оставался только `tag=a`.
    """
    params: QueryParams = {}

    for key, value in request.url.params.multi_items():
        existing = params.get(key)
        if existing is None:
            params[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            params[key] = [existing, value]

    return sanitizer.sanitize(params, sanitize_keys)


def encode_query_params(params: QueryParams) -> str:
    """Собрать query строку, не схлопывая повторяющиеся ключи."""
    pairs: list[tuple[str, str]] = []

    for key, value in params.items():
        if isinstance(value, list):
            pairs.extend((key, item) for item in value)
        else:
            pairs.append((key, value))

    # safe="*", чтобы маска **** не превратилась в %2A%2A%2A%2A
    return urlencode(pairs, safe="*")
