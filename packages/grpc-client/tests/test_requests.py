import grpc
import pytest
from api.examples.sub.message_pb2 import StringMessage
from grpc_client import MessageUndefinedError, ResponseStatusError

from .assertions import assert_that
from .clients import ABitOfEverythingServiceClient, GRPCbinServiceClient
from .support import code_number


def test_returns_ok_status_for_unary_request(boe_client: ABitOfEverythingServiceClient) -> None:
    """A successful unary request finishes with status OK."""
    response = boe_client.echo(StringMessage(value="Per aspera ad astra"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_returns_echoed_message_for_unary_request(boe_client: ABitOfEverythingServiceClient) -> None:
    """The service returns the sent message."""
    sent_value = "Veni, vidi, vici"

    response = boe_client.echo(StringMessage(value=sent_value))

    assert_that(response.message().value).is_equal_to(sent_value)


def test_marks_successful_response_as_ok(boe_client: ABitOfEverythingServiceClient) -> None:
    """A successful response is marked successful."""
    response = boe_client.echo(StringMessage(value="Cogito ergo sum"))

    assert_that(response.ok).is_true()


def test_returns_empty_details_for_successful_request(boe_client: ABitOfEverythingServiceClient) -> None:
    """A successful response has no status explanation."""
    response = boe_client.echo(StringMessage(value="Alea iacta est"))

    assert_that(response).has_details("")


def test_returns_message_of_empty_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """A successful response without fields remains accessible as a message."""
    response = grpcbin_client.empty()

    assert_that(response.message()).is_not_none()


def test_returns_requested_error_code(grpcbin_client: GRPCbinServiceClient) -> None:
    """The service responds with the error code it was asked to return."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="ничего не нашлось")

    assert_that(response).has_status_code(grpc.StatusCode.NOT_FOUND)


def test_returns_error_reason_in_details(grpcbin_client: GRPCbinServiceClient) -> None:
    """The service error text appears in response details."""
    reason = "склад закрыт на учет"

    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.UNAVAILABLE), reason=reason)

    assert_that(response).has_details(reason)


def test_marks_failed_response_as_not_ok(grpcbin_client: GRPCbinServiceClient) -> None:
    """A failed response is not marked successful."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.PERMISSION_DENIED), reason="нет прав")

    assert_that(response.ok).is_false()


def test_keeps_original_error_in_failed_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """A failed response retains the original gRPC exception."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.INTERNAL), reason="сломалось")

    assert_that(response.error).is_instance_of(grpc.RpcError)


def test_rejects_message_access_for_failed_request(grpcbin_client: GRPCbinServiceClient) -> None:
    """Accessing the message of an unsuccessful response raises an error."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.ABORTED), reason="прервано")

    with pytest.raises(MessageUndefinedError):
        response.message()


def test_raises_for_failed_status(grpcbin_client: GRPCbinServiceClient) -> None:
    """Checking an unsuccessful response status raises an error."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.DATA_LOSS), reason="данные потеряны")

    with pytest.raises(ResponseStatusError):
        response.raise_for_status()


def test_returns_itself_when_status_is_ok(boe_client: ABitOfEverythingServiceClient) -> None:
    """Checking a successful response status returns the same response."""
    response = boe_client.echo(StringMessage(value="Dum spiro spero"))

    assert_that(response.raise_for_status()).is_same_as(response)


def test_returns_parsed_message(boe_client: ABitOfEverythingServiceClient) -> None:
    """The parser is applied to the response message."""
    response = boe_client.echo(StringMessage(value="ad hoc"))

    assert_that(response.with_parser(lambda msg: msg.value.upper()).parse()).is_equal_to("AD HOC")


def test_keeps_status_in_parsed_response(boe_client: ABitOfEverythingServiceClient) -> None:
    """A parsed response preserves the original response status."""
    response = boe_client.echo(StringMessage(value="in vino veritas"))

    assert_that(response.with_parser(lambda msg: msg.value)).has_status_code(grpc.StatusCode.OK)
