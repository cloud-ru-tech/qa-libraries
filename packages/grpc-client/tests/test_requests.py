import grpc
import pytest
from api.examples.sub.message_pb2 import StringMessage
from grpc_client import MessageUndefinedError, ResponseStatusError

from .assertions import assert_that
from .clients import ABitOfEverythingServiceClient, GRPCbinServiceClient
from .support import code_number


def test_returns_ok_status_for_unary_request(boe_client: ABitOfEverythingServiceClient) -> None:
    """Успешный унарный запрос завершается статусом OK."""
    response = boe_client.echo(StringMessage(value="Per aspera ad astra"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_returns_echoed_message_for_unary_request(boe_client: ABitOfEverythingServiceClient) -> None:
    """Сервис возвращает отправленное сообщение."""
    sent_value = "Veni, vidi, vici"

    response = boe_client.echo(StringMessage(value=sent_value))

    assert_that(response.message().value).is_equal_to(sent_value)


def test_marks_successful_response_as_ok(boe_client: ABitOfEverythingServiceClient) -> None:
    """Успешный ответ помечается признаком успеха."""
    response = boe_client.echo(StringMessage(value="Cogito ergo sum"))

    assert_that(response.ok).is_true()


def test_returns_empty_details_for_successful_request(boe_client: ABitOfEverythingServiceClient) -> None:
    """У успешного ответа нет пояснения к статусу."""
    response = boe_client.echo(StringMessage(value="Alea iacta est"))

    assert_that(response).has_details("")


def test_returns_message_of_empty_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """Успешный ответ без полей остается доступным как сообщение."""
    response = grpcbin_client.empty()

    assert_that(response.message()).is_not_none()


def test_returns_requested_error_code(grpcbin_client: GRPCbinServiceClient) -> None:
    """Сервис отвечает тем кодом ошибки, который его попросили вернуть."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="ничего не нашлось")

    assert_that(response).has_status_code(grpc.StatusCode.NOT_FOUND)


def test_returns_error_reason_in_details(grpcbin_client: GRPCbinServiceClient) -> None:
    """Текст ошибки от сервиса попадает в детали ответа."""
    reason = "склад закрыт на учет"

    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.UNAVAILABLE), reason=reason)

    assert_that(response).has_details(reason)


def test_marks_failed_response_as_not_ok(grpcbin_client: GRPCbinServiceClient) -> None:
    """Ответ с ошибкой не помечается признаком успеха."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.PERMISSION_DENIED), reason="нет прав")

    assert_that(response.ok).is_false()


def test_keeps_original_error_in_failed_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """Ответ с ошибкой хранит исходное исключение gRPC."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.INTERNAL), reason="сломалось")

    assert_that(response.error).is_instance_of(grpc.RpcError)


def test_rejects_message_access_for_failed_request(grpcbin_client: GRPCbinServiceClient) -> None:
    """Обращение к сообщению неуспешного ответа завершается ошибкой."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.ABORTED), reason="прервано")

    with pytest.raises(MessageUndefinedError):
        response.message()


def test_raises_for_failed_status(grpcbin_client: GRPCbinServiceClient) -> None:
    """Проверка статуса неуспешного ответа завершается ошибкой."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.DATA_LOSS), reason="данные потеряны")

    with pytest.raises(ResponseStatusError):
        response.raise_for_status()


def test_returns_itself_when_status_is_ok(boe_client: ABitOfEverythingServiceClient) -> None:
    """Проверка статуса успешного ответа возвращает тот же ответ."""
    response = boe_client.echo(StringMessage(value="Dum spiro spero"))

    assert_that(response.raise_for_status()).is_same_as(response)


def test_returns_parsed_message(boe_client: ABitOfEverythingServiceClient) -> None:
    """Функция разбора применяется к ответному сообщению."""
    response = boe_client.echo(StringMessage(value="ad hoc"))

    assert_that(response.with_parser(lambda msg: msg.value.upper()).parse()).is_equal_to("AD HOC")


def test_keeps_status_in_parsed_response(boe_client: ABitOfEverythingServiceClient) -> None:
    """Ответ с функцией разбора сохраняет статус исходного ответа."""
    response = boe_client.echo(StringMessage(value="in vino veritas"))

    assert_that(response.with_parser(lambda msg: msg.value)).has_status_code(grpc.StatusCode.OK)
