from __future__ import annotations

from typing import TYPE_CHECKING

from ._utils import body_preview, request_method, request_url

if TYPE_CHECKING:
    from httpx import Response


class ResponseParseError(Exception):
    """Не удалось разобрать тело ответа на запрос.

    Оборачивает исходную ошибку парсинга, добавляя к ней HTTP-контекст: метод, URL,
    статус и тело ответа. Исходное исключение доступно в атрибуте `cause` и в `__cause__`.

    Тело в сообщении обрезается до `BODY_PREVIEW_LIMIT` байт. Если ответ получен
    стримингом и тело ещё не прочитано, вместо него подставляется `<streamed content>`.
    """

    BODY_PREVIEW_LIMIT = 512

    def __init__(self, response: Response, cause: Exception) -> None:
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        :param cause: значение настройки ``cause``.
        """
        self.response = response
        self.cause = cause
        super().__init__(self._build_message(response, cause))

    @classmethod
    def _build_message(cls, response: Response, cause: Exception) -> str:
        return (
            "не удалось разобрать тело ответа\n"
            f"  {request_method(response)} {request_url(response)} -> {response.status_code}\n"
            f"  Body: {body_preview(response, cls.BODY_PREVIEW_LIMIT)}\n"
            f"  Причина: {cause}"
        )
