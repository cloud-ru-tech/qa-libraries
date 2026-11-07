from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import ResponseNotRead

if TYPE_CHECKING:
    from httpx import Response

UNKNOWN = "?"
STREAMED_BODY = "<streamed content>"
DEFAULT_ENCODING = "utf-8"


def request_method(response: Response) -> str:
    """Вернуть HTTP-метод запроса, на который получен ответ.

    :param response: ответ на запрос
    :returns: метод запроса или `?`, если ответ создан вручную и запрос в нём не проставлен
    """
    try:
        return response.request.method
    except RuntimeError:
        return UNKNOWN


def request_url(response: Response) -> str:
    """Вернуть URL запроса, на который получен ответ.

    :param response: ответ на запрос
    :returns: URL запроса или `?`, если ответ создан вручную и запрос в нём не проставлен
    """
    try:
        return str(response.url)
    except RuntimeError:
        return UNKNOWN


def body_preview(response: Response, limit: int) -> str:
    """Вернуть тело ответа для подстановки в сообщение об ошибке.

    :param response: ответ на запрос
    :param limit: максимальный размер тела в результате, в байтах
    :returns: тело ответа, обрезанное до `limit` байт, или заглушка для непрочитанного стрима
    """
    try:
        content = response.content
    except ResponseNotRead:
        return STREAMED_BODY

    encoding = response.encoding or DEFAULT_ENCODING
    if len(content) <= limit:
        return content.decode(encoding, errors="replace")

    # Режем байты до декодирования: `response.text` развернул бы в память всё тело целиком
    # ради нескольких сотен символов. errors="replace" гасит символ, разрезанный по границе.
    head = content[:limit].decode(encoding, errors="replace")
    return f"{head}... (обрезано, всего {len(content)} байт)"
