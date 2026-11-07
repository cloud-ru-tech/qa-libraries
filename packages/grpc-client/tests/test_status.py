import grpc
from grpc_client.status import STATUS_DETAILS_KEY, error_status_from_metadata

from .assertions import assert_that
from .clients import ABitOfEverythingServiceClient, GRPCbinServiceClient
from .support import code_number


def test_returns_error_status_for_rich_error(boe_client: ABitOfEverythingServiceClient) -> None:
    """Ответ с расширенными деталями отдает разобранный статус ошибки."""
    response = boe_client.error_with_details()

    assert_that(response.error_status).is_not_none()


def test_returns_error_message_of_rich_error(boe_client: ABitOfEverythingServiceClient) -> None:
    """Расширенный статус содержит текст ошибки, заданный сервисом."""
    response = boe_client.error_with_details()

    assert_that(response).has_error_message("with details")


def test_returns_error_details_of_rich_error(boe_client: ABitOfEverythingServiceClient) -> None:
    """Расширенный статус содержит типизированные подробности ошибки."""
    response = boe_client.error_with_details()

    assert_that(response).has_error_details()


def test_finds_error_detail_by_type(boe_client: ABitOfEverythingServiceClient) -> None:
    """Подробность ошибки находится по типу сообщения."""
    response = boe_client.error_with_details()

    assert_that(response).has_error_detail_of_first_type()


def test_returns_no_error_status_for_plain_error(grpcbin_client: GRPCbinServiceClient) -> None:
    """Обычная ошибка без google.rpc.Status не дает расширенного статуса."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="просто ошибка")

    assert_that(response.error_status).is_none()


def test_returns_no_error_status_for_successful_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """У успешного ответа расширенного статуса нет."""
    response = grpcbin_client.empty()

    assert_that(response.error_status).is_none()


def test_ignores_malformed_status_payload() -> None:
    """Нечитаемое значение расширенного статуса не приводит к ошибке."""
    assert_that(error_status_from_metadata([(STATUS_DETAILS_KEY, b"\xff\xfe not a protobuf")])).is_none()


def test_ignores_missing_status_key() -> None:
    """Отсутствие ключа расширенного статуса не приводит к ошибке."""
    assert_that(error_status_from_metadata([("content-type", "application/grpc")])).is_none()
