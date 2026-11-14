import grpc
import pytest
from api import grpcbin_pb2
from grpc_client import CallOptions, options

from .assertions import assert_that
from .clients import GRPCbinServiceClient


def test_closes_own_channel(service_addr: str) -> None:
    """A client-created channel closes with the client and accepts no further requests."""
    client = GRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel())
    client.close()

    with pytest.raises(ValueError, match="closed channel"):
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="после закрытия"))


def test_keeps_external_channel_open(service_addr: str) -> None:
    """An externally supplied channel keeps working after the client closes."""
    with grpc.insecure_channel(service_addr) as channel:
        client = GRPCbinServiceClient.from_channel(channel)
        client.close()

        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="канал снаружи"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_sends_request_through_external_channel(service_addr: str) -> None:
    """The client works over an existing channel."""
    with grpc.insecure_channel(service_addr) as channel:
        client = GRPCbinServiceClient.from_channel(channel)

        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="готовый канал"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_applies_client_timeout_to_stream(service_addr: str, dummy_message: grpcbin_pb2.DummyMessage) -> None:
    """The client timeout is applied to the call."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_timeout(0.05),
    ) as client:
        response = client.send_server_stream(dummy_message).collect()

    assert_that(response).has_status_code(grpc.StatusCode.DEADLINE_EXCEEDED)


def test_overrides_client_timeout_per_call(service_addr: str, dummy_message: grpcbin_pb2.DummyMessage) -> None:
    """A call timeout overrides the client setting."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_timeout(0.05),
    ) as client:
        response = client.send_server_stream(dummy_message, CallOptions(timeout=30)).collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_reports_unavailable_for_unknown_address() -> None:
    """A request to an unavailable address finishes with status UNAVAILABLE."""
    with GRPCbinServiceClient.from_addr(
        "127.0.0.1:1",
        options.with_insecure_channel(),
        options.with_timeout(2),
    ) as client:
        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="некуда идти"))

    assert_that(response).has_status_code(grpc.StatusCode.UNAVAILABLE)


def test_uses_secure_channel_by_default(service_addr: str) -> None:
    """Channels use encryption by default, so an unencrypted service is unavailable."""
    with GRPCbinServiceClient.from_addr(service_addr, options.with_timeout(5)) as client:
        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="через tls"))

    assert_that(response.ok).is_false()


def test_exposes_channel_of_client(service_addr: str) -> None:
    """The client exposes the channel used to send requests."""
    with GRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        assert_that(client.channel).is_not_none()
