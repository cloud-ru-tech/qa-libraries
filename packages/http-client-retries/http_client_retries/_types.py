from typing import TypeGuard, cast

from httpx import Request, Response


def is_http_request(value: object) -> TypeGuard[Request]:
    """Проверить тип запроса HTTPX.

    :param value: произвольный аргумент вызова.
    :return: является ли аргумент запросом HTTPX.
    """
    return isinstance(value, cast("type[object]", Request))


def is_http_response(value: object) -> TypeGuard[Response]:
    """Проверить тип ответа HTTPX.

    :param value: результат вызова.
    :return: является ли результат ответом HTTPX.
    """
    return isinstance(value, cast("type[object]", Response))
