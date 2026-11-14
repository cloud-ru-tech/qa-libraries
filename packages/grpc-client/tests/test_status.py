import grpc
from grpc_client.status import STATUS_DETAILS_KEY, error_status_from_metadata

from .assertions import assert_that
from .clients import ABitOfEverythingServiceClient, GRPCbinServiceClient
from .support import code_number


def test_returns_error_status_for_rich_error(boe_client: ABitOfEverythingServiceClient) -> None:
    """A response with rich details exposes the parsed error status."""
    response = boe_client.error_with_details()

    assert_that(response.error_status).is_not_none()


def test_returns_error_message_of_rich_error(boe_client: ABitOfEverythingServiceClient) -> None:
    """The rich status contains the service error text."""
    response = boe_client.error_with_details()

    assert_that(response).has_error_message("with details")


def test_returns_error_details_of_rich_error(boe_client: ABitOfEverythingServiceClient) -> None:
    """The rich status contains typed error details."""
    response = boe_client.error_with_details()

    assert_that(response).has_error_details()


def test_finds_error_detail_by_type(boe_client: ABitOfEverythingServiceClient) -> None:
    """An error detail is found by its message type."""
    response = boe_client.error_with_details()

    assert_that(response).has_error_detail_of_first_type()


def test_returns_no_error_status_for_plain_error(grpcbin_client: GRPCbinServiceClient) -> None:
    """A regular error without google.rpc.Status provides no rich status."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="просто ошибка")

    assert_that(response.error_status).is_none()


def test_returns_no_error_status_for_successful_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """A successful response has no rich status."""
    response = grpcbin_client.empty()

    assert_that(response.error_status).is_none()


def test_ignores_malformed_status_payload() -> None:
    """An unreadable rich status value does not cause an error."""
    assert_that(error_status_from_metadata([(STATUS_DETAILS_KEY, b"\xff\xfe not a protobuf")])).is_none()


def test_ignores_missing_status_key() -> None:
    """A missing rich status key does not cause an error."""
    assert_that(error_status_from_metadata([("content-type", "application/grpc")])).is_none()
