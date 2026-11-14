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

    _Builder = AssertionBuilder[object]
else:
    _Builder = AssertionBuilder


class GRPCAssertions(_Builder):
    """Assertions about gRPC responses and client logs."""

    def has_status_code(self, expected: grpc.StatusCode) -> Self:
        """Check the response status code.

        :param expected: expected status code
        :return: assertion builder for chaining
        """
        actual = cast("GRPCResponse[Message]", self.val).status_code
        if actual is not expected:
            self.error(f"Ожидался код статуса <{expected.name}>, а был <{actual.name}>")
        return self

    def has_details(self, expected: str) -> Self:
        """Check the text explaining the response status.

        :param expected: expected text
        :return: assertion builder for chaining
        """
        actual = cast("GRPCResponse[Message]", self.val).details
        if actual != expected:
            self.error(f"Ожидались детали ответа <{expected}>, а были <{actual}>")
        return self

    def has_metadata_value(self, key: str, expected: str | bytes) -> Self:
        """Check a key value in response metadata.

        :param key: metadata key name
        :param expected: expected value
        :return: assertion builder for chaining
        """
        values = cast("GRPCResponse[Message]", self.val).trailing_metadata.get_all(key)
        if expected not in values:
            self.error(f"Ожидалось значение <{expected!r}> ключа <{key}>, а были значения <{list(values)!r}>")
        return self

    def received_metadata(self, key: str, expected: str) -> Self:
        """Check whether the service received request metadata with the specified value.

        Applied to responses from the method that returns request metadata.

        :param key: metadata key name
        :param expected: expected value
        :return: assertion builder for chaining
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key not in received:
            self.error(f"Ожидался ключ <{key}> в метаданных запроса, а сервис получил <{sorted(received)}>")

        values = list(received[key].values)
        if expected not in values:
            self.error(f"Ожидалось значение <{expected}> ключа <{key}>, а сервис получил <{values}>")
        return self

    def received_all_metadata(self, key: str, expected: list[str]) -> Self:
        """Check all values for a key received by the service.

        :param key: metadata key name
        :param expected: expected values in sending order
        :return: assertion builder for chaining
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key not in received:
            self.error(f"Ожидался ключ <{key}> в метаданных запроса, а сервис получил <{sorted(received)}>")

        values = list(received[key].values)
        if values != expected:
            self.error(f"Ожидались значения <{expected}> ключа <{key}>, а сервис получил <{values}>")
        return self

    def received_metadata_matching(self, key: str, pattern: str) -> Self:
        """Check whether a request metadata value matches a pattern.

        :param key: metadata key name
        :param pattern: regular expression the value must match
        :return: assertion builder for chaining
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key not in received:
            self.error(f"Ожидался ключ <{key}> в метаданных запроса, а сервис получил <{sorted(received)}>")

        values = list(received[key].values)
        if not any(re.fullmatch(pattern, value) for value in values):
            self.error(f"Ожидалось значение ключа <{key}> по шаблону <{pattern}>, а сервис получил <{values}>")
        return self

    def has_no_metadata(self, key: str) -> Self:
        """Check whether the service received no request metadata with the specified key.

        :param key: metadata key name
        :return: assertion builder for chaining
        """
        received = cast("GRPCResponse[HeadersMessage]", self.val).message().Metadata
        if key in received:
            self.error(f"Ключа <{key}> не должно быть в метаданных запроса, а сервис получил <{sorted(received)}>")
        return self

    def has_error_message(self, expected: str) -> Self:
        """Check the error text in the rich google.rpc.Status.

        :param expected: expected error text
        :return: assertion builder for chaining
        """
        status = cast("GRPCResponse[Message]", self.val).error_status
        if status is None:
            self.error(f"Ожидался расширенный статус ошибки с текстом <{expected}>, а его не было")
        elif status.message != expected:
            self.error(f"Ожидался текст ошибки <{expected}>, а был <{status.message}>")
        return self

    def has_error_details(self) -> Self:
        """Check whether the rich error status contains typed details.

        :return: assertion builder for chaining
        """
        status = cast("GRPCResponse[Message]", self.val).error_status
        if status is None:
            self.error("Ожидался расширенный статус ошибки, а его не было")
        elif not status.details:
            self.error("Ожидались подробности ошибки, а их не было")
        return self

    def has_error_detail_of_first_type(self) -> Self:
        """Check whether an error detail is found by its message type.

        :return: assertion builder for chaining
        """
        status = cast("GRPCResponse[Message]", self.val).error_status
        if status is None or not status.details:
            self.error("Ожидались подробности ошибки, а их не было")
            return self

        detail_type = type(status.details[0])
        if status.of_type(detail_type) is None:
            self.error(f"Подробность ошибки типа <{detail_type.__name__}> не нашлась по своему типу")
        return self

    def logged(self, expected: str) -> Self:
        """Check whether the log contains a substring.

        :param expected: expected substring
        :return: assertion builder for chaining
        """
        log = self._log_text()
        if expected not in log:
            self.error(f"Ожидалась в логе подстрока <{expected}>, а лог был таким: <{log}>")
        return self

    def not_logged(self, unexpected: str) -> Self:
        """Check whether the log does not contain a substring.

        :param unexpected: substring that must be absent
        :return: assertion builder for chaining
        """
        log = self._log_text()
        if unexpected in log:
            self.error(f"Подстроки <{unexpected}> не должно быть в логе, а лог был таким: <{log}>")
        return self

    def has_log_records(self, expected_count: int) -> Self:
        """Check the number of nonempty log lines.

        :param expected_count: expected line count
        :return: assertion builder for chaining
        """
        records = [line for line in self._log_text().splitlines() if line.strip()]
        if len(records) != expected_count:
            self.error(f"Ожидалось строк в логе <{expected_count}>, а было <{len(records)}>: <{records}>")
        return self

    def _log_text(self) -> str:
        return self.val.getvalue() if isinstance(self.val, StringIO) else str(self.val)


def assert_that(val: object, description: str = "") -> GRPCAssertions:
    """Start assertions extended with gRPC checks.

    :param val: value to check
    :param description: description inserted into the error message
    :return: assertion builder
    """
    return GRPCAssertions(val, description)
