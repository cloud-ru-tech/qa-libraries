from __future__ import annotations

import re
from io import StringIO
from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder

if TYPE_CHECKING:
    import grpc
    from api.grpcbin_pb2 import HeadersMessage
    from google.protobuf.message import Message
    from grpc_client import GRPCResponse
    from http_client_auth import AuthStore, Token

    _Builder = AssertionBuilder[object]
else:
    _Builder = AssertionBuilder


class GRPCAssertions(_Builder):
    """Утверждения об ответах gRPC и логах клиента."""

    def has_status_code(self, expected: grpc.StatusCode) -> Self:
        """Проверить код статуса ответа.

        :param expected: ожидаемый код статуса
        :return: билдер утверждений для продолжения цепочки
        """
        actual = cast("GRPCResponse[Message]", self.val).status_code
        if actual is not expected:
            self.error(f"Ожидался код статуса <{expected.name}>, а был <{actual.name}>")
        return self

    def has_details(self, expected: str) -> Self:
        """Проверить текст, поясняющий статус ответа.

        :param expected: ожидаемый текст
        :return: билдер утверждений для продолжения цепочки
        """
        actual = cast("GRPCResponse[Message]", self.val).details
        if actual != expected:
            self.error(f"Ожидались детали ответа <{expected}>, а были <{actual}>")
        return self

    def has_metadata_value(self, key: str, expected: str | bytes) -> Self:
        """Проверить значение ключа в метаданных ответа.

        :param key: имя ключа метаданных
        :param expected: ожидаемое значение
        :return: билдер утверждений для продолжения цепочки
        """
        values = cast("GRPCResponse[Message]", self.val).trailing_metadata.get_all(key)
        if expected not in values:
            self.error(f"Ожидалось значение <{expected!r}> ключа <{key}>, а были значения <{list(values)!r}>")
        return self

    def received_metadata(self, key: str, expected: str) -> Self:
        """Проверить, что сервис увидел в запросе метаданные с указанным значением.

        Применяется к ответу метода, возвращающего метаданные запроса.

        :param key: имя ключа метаданных
        :param expected: ожидаемое значение
        :return: билдер утверждений для продолжения цепочки
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key not in received:
            self.error(f"Ожидался ключ <{key}> в метаданных запроса, а сервис получил <{sorted(received)}>")

        values = list(received[key].values)
        if expected not in values:
            self.error(f"Ожидалось значение <{expected}> ключа <{key}>, а сервис получил <{values}>")
        return self

    def received_metadata_matching(self, key: str, pattern: str) -> Self:
        """Проверить, что значение метаданных запроса совпадает с шаблоном.

        :param key: имя ключа метаданных
        :param pattern: регулярное выражение, которому должно соответствовать значение
        :return: билдер утверждений для продолжения цепочки
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key not in received:
            self.error(f"Ожидался ключ <{key}> в метаданных запроса, а сервис получил <{sorted(received)}>")

        values = list(received[key].values)
        if not any(re.fullmatch(pattern, value) for value in values):
            self.error(f"Ожидалось значение ключа <{key}> по шаблону <{pattern}>, а сервис получил <{values}>")
        return self

    def has_no_metadata(self, key: str) -> Self:
        """Проверить, что сервис не увидел в запросе указанный ключ метаданных.

        :param key: имя ключа метаданных
        :return: билдер утверждений для продолжения цепочки
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key in received:
            self.error(f"Ключа <{key}> не должно быть в метаданных запроса, а сервис получил <{sorted(received)}>")
        return self

    def has_error_message(self, expected: str) -> Self:
        """Проверить текст ошибки в расширенном статусе google.rpc.Status.

        :param expected: ожидаемый текст ошибки
        :return: билдер утверждений для продолжения цепочки
        """
        status = cast("GRPCResponse[Message]", self.val).error_status
        if status is None:
            self.error(f"Ожидался расширенный статус ошибки с текстом <{expected}>, а его не было")
        elif status.message != expected:
            self.error(f"Ожидался текст ошибки <{expected}>, а был <{status.message}>")
        return self

    def has_error_details(self) -> Self:
        """Проверить, что расширенный статус ошибки содержит типизированные подробности.

        :return: билдер утверждений для продолжения цепочки
        """
        status = cast("GRPCResponse[Message]", self.val).error_status
        if status is None:
            self.error("Ожидался расширенный статус ошибки, а его не было")
        elif not status.details:
            self.error("Ожидались подробности ошибки, а их не было")
        return self

    def has_error_detail_of_first_type(self) -> Self:
        """Проверить, что подробность ошибки находится по типу своего сообщения.

        :return: билдер утверждений для продолжения цепочки
        """
        status = cast("GRPCResponse[Message]", self.val).error_status
        if status is None or not status.details:
            self.error("Ожидались подробности ошибки, а их не было")
            return self

        detail_type = type(status.details[0])
        if status.of_type(detail_type) is None:
            self.error(f"Подробность ошибки типа <{detail_type.__name__}> не нашлась по своему типу")
        return self

    def stores_token(self, key: str, expected: str) -> Self:
        """Проверить, какой токен лежит в хранилище по ключу.

        :param key: ключ, под которым хранится токен
        :param expected: ожидаемое значение токена доступа
        :return: билдер утверждений для продолжения цепочки
        """
        token = cast("AuthStore", self.val).get(key)
        if token is None:
            self.error(f"Ожидался токен <{expected}> по ключу <{key}>, а хранилище оказалось пустым")
        elif token.access_token != expected:
            self.error(f"Ожидался токен <{expected}> по ключу <{key}>, а был <{token.access_token}>")
        return self

    def has_access_token(self, expected: str) -> Self:
        """Проверить значение токена доступа.

        :param expected: ожидаемое значение токена
        :return: билдер утверждений для продолжения цепочки
        """
        if self.val is None:
            self.error(f"Ожидался токен <{expected}>, а его не было")
        elif cast("Token", self.val).access_token != expected:
            self.error(f"Ожидался токен <{expected}>, а был <{cast('Token', self.val).access_token}>")
        return self

    def logged(self, expected: str) -> Self:
        """Проверить, что подстрока встречается в логе.

        :param expected: ожидаемая подстрока
        :return: билдер утверждений для продолжения цепочки
        """
        log = self._log_text()
        if expected not in log:
            self.error(f"Ожидалась в логе подстрока <{expected}>, а лог был таким: <{log}>")
        return self

    def not_logged(self, unexpected: str) -> Self:
        """Проверить, что подстрока не встречается в логе.

        :param unexpected: подстрока, которой не должно быть
        :return: билдер утверждений для продолжения цепочки
        """
        log = self._log_text()
        if unexpected in log:
            self.error(f"Подстроки <{unexpected}> не должно быть в логе, а лог был таким: <{log}>")
        return self

    def has_log_records(self, expected_count: int) -> Self:
        """Проверить количество непустых строк в логе.

        :param expected_count: ожидаемое количество строк
        :return: билдер утверждений для продолжения цепочки
        """
        records = [line for line in self._log_text().splitlines() if line.strip()]
        if len(records) != expected_count:
            self.error(f"Ожидалось строк в логе <{expected_count}>, а было <{len(records)}>: <{records}>")
        return self

    def _log_text(self) -> str:
        return self.val.getvalue() if isinstance(self.val, StringIO) else str(self.val)


def assert_that(val: object, description: str = "") -> GRPCAssertions:
    """Начать проверку с утверждениями, дополненными проверками gRPC.

    :param val: проверяемое значение
    :param description: описание, подставляемое в сообщение об ошибке
    :return: билдер утверждений
    """
    return GRPCAssertions(val, description)
