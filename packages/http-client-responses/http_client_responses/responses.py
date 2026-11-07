from __future__ import annotations

from typing import TYPE_CHECKING, Self, TypeVar, cast

from pydantic import BaseModel

from ._utils import request_method, request_url
from .exceptions import ResponseParseError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta

    from httpx import Cookies, Headers, Request, Response

RT = TypeVar("RT")  # Response Type
RS = TypeVar("RS", bound=BaseModel)  # Response Schema


class _Unset:
    """Маркер «значение ещё не вычислено»: None — валидный результат парсинга, отличать его нужно чем-то другим."""


_UNSET = _Unset()


class ResponseWrapper:
    """Базовый класс-обёртка над ответом на запрос."""

    def __init__(self, response: Response) -> None:
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        """
        self.response = response

    def __repr__(self) -> str:
        """Получить HTTP-контекст ответа для диагностики."""
        method = request_method(self.response)
        return f"<{type(self).__name__} {method} {request_url(self.response)} -> {self.status_code}>"

    @property
    def status_code(self) -> int:
        """HTTP-код ответа."""
        return self.response.status_code

    @property
    def reason_phrase(self) -> str:
        """Описание HTTP-кода ответа."""
        return self.response.reason_phrase

    @property
    def headers(self) -> Headers:
        """Заголовки ответа.

        `httpx.Headers`, а не `dict`: доступ по ключу регистронезависим, а `get_list()` отдаёт
        все значения заголовка, который сервер прислал несколько раз (например, `Set-Cookie`).
        """
        return self.response.headers

    @property
    def raw_headers(self) -> dict[str, str]:
        """Заголовки ответа обычным словарём.

        Повторяющиеся заголовки склеиваются в одну строку через запятую — если это важно,
        используйте `headers`.
        """
        return dict(self.response.headers)

    @property
    def cookies(self) -> Cookies:
        """Cookies ответа."""
        return self.response.cookies

    @property
    def content(self) -> bytes:
        """Тело ответа в байтах.

        :raises httpx.ResponseNotRead: если ответ получен стримингом и тело ещё не прочитано
        """
        return self.response.content

    @property
    def text(self) -> str:
        """Тело ответа строкой.

        :raises httpx.ResponseNotRead: если ответ получен стримингом и тело ещё не прочитано
        """
        return self.response.text

    @property
    def url(self) -> str:
        """URL запроса, на который получен ответ.

        :raises RuntimeError: если ответ создан вручную и запрос в нём не проставлен
        """
        return str(self.response.url)

    @property
    def request(self) -> Request:
        """Запрос, на который получен ответ.

        :raises RuntimeError: если ответ создан вручную и запрос в нём не проставлен
        """
        return self.response.request

    @property
    def elapsed(self) -> timedelta:
        """Время между отправкой запроса и получением ответа.

        :raises RuntimeError: если тело ответа ещё не прочитано целиком
        """
        return self.response.elapsed

    @property
    def is_success(self) -> bool:
        """Проверить, что статус находится в диапазоне 2xx."""
        return self.response.is_success

    @property
    def is_error(self) -> bool:
        """Проверить, что статус находится в диапазоне 4xx или 5xx."""
        return self.response.is_error

    @property
    def is_client_error(self) -> bool:
        """Проверить, что статус находится в диапазоне 4xx."""
        return self.response.is_client_error

    @property
    def is_server_error(self) -> bool:
        """Проверить, что статус находится в диапазоне 5xx."""
        return self.response.is_server_error

    def raise_for_status(self) -> Self:
        """Проверить статус ответа.

        Возвращает сам объект-обёртку, чтобы проверку можно было выстроить в цепочку:
        `response.raise_for_status().model()`.

        :raises httpx.HTTPStatusError: если статус ответа не 2xx, включая 1xx и редиректы
        :raises RuntimeError: если ответ создан вручную и запрос в нём не проставлен
        :returns: этот же объект
        """
        self.response.raise_for_status()
        return self

    def json(self) -> object:
        """Разобрать тело ответа как JSON без валидации схемы.

        :raises ResponseParseError: если тело не является валидным JSON
        :returns: разобранное тело ответа
        """
        try:
            return cast("object", self.response.json())
        except Exception as exc:
            raise ResponseParseError(self.response, exc) from exc


class GenericResponse[RT](ResponseWrapper):
    """Ответ на запрос вместе с методом парсинга данных из тела."""

    def __init__(self, response: Response, parser: Callable[[Response], RT]) -> None:
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        :param parser: значение настройки ``parser``.
        """
        super().__init__(response)
        self.parser = parser
        self._parsed: RT | _Unset = _UNSET

    def parse(self) -> RT:
        """Разобрать тело ответа.

        Результат вычисляется один раз и переиспользуется при повторных вызовах.

        :raises ResponseParseError: если парсер не смог разобрать тело
        :returns: результат работы парсера
        """
        if self._parsed is _UNSET:
            try:
                self._parsed = self.parser(self.response)
            except Exception as exc:
                raise ResponseParseError(self.response, exc) from exc
        return cast("RT", self._parsed)


class JsonResponse[RS: BaseModel](GenericResponse[RS]):
    """Ответ на запрос вместе с JSON схемой тела ответа в виде pydantic модели."""

    def __init__(self, response: Response, schema: type[RS]) -> None:
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        :param schema: значение настройки ``schema``.
        """
        super().__init__(response, lambda r: schema.model_validate_json(r.content))
        self.schema = schema

    def model(self) -> RS:
        """Разобрать тело ответа в pydantic модель.

        :raises ResponseParseError: если тело не соответствует схеме
        :returns: заполненная модель схемы ответа
        """
        return self.parse()
