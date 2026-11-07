from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder
from pytest_httpx import HTTPXMock

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx

    _Assertions = AssertionBuilder[object]
else:
    _Assertions = AssertionBuilder


class HttpxMockAssertions(_Assertions):
    """Утверждения о запросах, перехваченных pytest-httpx."""

    def sent_json_to(self, path: str, expected: Mapping[str, object]) -> Self:
        """Проверить, что по пути ушел запрос с ожидаемым JSON-телом.

        :param path: путь запроса без схемы и хоста
        :param expected: ожидаемое тело запроса
        :return: билдер утверждений для продолжения цепочки
        """
        bodies = [cast("object", json.loads(request.content)) for request in self._requests_to(path)]
        if expected not in bodies:
            self.error(f"Ожидался запрос на <{path}> с телом <{expected}>, а отправлены были <{bodies}>")
        return self

    def sent_bearer_token_to(self, path: str, expected: str) -> Self:
        """Проверить, что по пути ушел запрос с указанным токеном в заголовке Authorization.

        :param path: путь запроса без схемы и хоста
        :param expected: ожидаемое значение токена доступа
        :return: билдер утверждений для продолжения цепочки
        """
        tokens = [cast("str | None", request.headers.get("Authorization")) for request in self._requests_to(path)]
        if f"Bearer {expected}" not in tokens:
            self.error(f"Ожидался запрос на <{path}> с токеном <{expected}>, а отправлены были <{tokens}>")
        return self

    def sent_requests_to(self, path: str, expected_count: int) -> Self:
        """Проверить количество запросов, ушедших по пути.

        :param path: путь запроса без схемы и хоста
        :param expected_count: ожидаемое количество запросов
        :return: билдер утверждений для продолжения цепочки
        """
        actual_count = len(self._requests_to(path))
        if actual_count != expected_count:
            self.error(f"Ожидалось запросов на <{path}>: <{expected_count}>, а отправлено было <{actual_count}>")
        return self

    def _requests_to(self, path: str) -> list[httpx.Request]:
        if not isinstance(self.val, HTTPXMock):
            message = "Утверждение применимо только к HTTPXMock"
            raise TypeError(message)

        return [request for request in self.val.get_requests() if request.url.path == path]


def assert_that(val: object, description: str = "") -> HttpxMockAssertions:
    """Начать проверку с утверждениями, дополненными проверками HTTP-запросов.

    :param val: проверяемое значение
    :param description: описание, подставляемое в сообщение об ошибке
    :return: билдер утверждений
    """
    return HttpxMockAssertions(val, description)
