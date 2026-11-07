import grpc
import pytest
from api import grpcbin_pb2
from grpc_client import CallOptions, options

from .assertions import assert_that
from .clients import GRPCbinServiceClient


def test_closes_own_channel(service_addr: str) -> None:
    """Канал, созданный клиентом, закрывается вместе с клиентом, и запросы через него больше не идут."""
    client = GRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel())
    client.close()

    with pytest.raises(ValueError, match="closed channel"):
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="после закрытия"))


def test_keeps_external_channel_open(service_addr: str) -> None:
    """Канал, переданный извне, продолжает работать после закрытия клиента."""
    with grpc.insecure_channel(service_addr) as channel:
        client = GRPCbinServiceClient.from_channel(channel)
        client.close()

        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="канал снаружи"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_sends_request_through_external_channel(service_addr: str) -> None:
    """Клиент работает поверх готового канала."""
    with grpc.insecure_channel(service_addr) as channel:
        client = GRPCbinServiceClient.from_channel(channel)

        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="готовый канал"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_applies_client_timeout_to_stream(service_addr: str, dummy_message: grpcbin_pb2.DummyMessage) -> None:
    """Ограничение времени, заданное клиенту, применяется к вызову."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_timeout(0.05),
    ) as client:
        response = client.send_server_stream(dummy_message).collect()

    assert_that(response).has_status_code(grpc.StatusCode.DEADLINE_EXCEEDED)


def test_overrides_client_timeout_per_call(service_addr: str, dummy_message: grpcbin_pb2.DummyMessage) -> None:
    """Ограничение времени вызова вытесняет настройку клиента."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_timeout(0.05),
    ) as client:
        response = client.send_server_stream(dummy_message, CallOptions(timeout=30)).collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_reports_unavailable_for_unknown_address() -> None:
    """Запрос к недоступному адресу завершается статусом UNAVAILABLE."""
    with GRPCbinServiceClient.from_addr(
        "127.0.0.1:1",
        options.with_insecure_channel(),
        options.with_timeout(2),
    ) as client:
        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="некуда идти"))

    assert_that(response).has_status_code(grpc.StatusCode.UNAVAILABLE)


def test_uses_secure_channel_by_default(service_addr: str) -> None:
    """По умолчанию канал шифруется, поэтому нешифрованный сервис недоступен."""
    with GRPCbinServiceClient.from_addr(service_addr, options.with_timeout(5)) as client:
        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="через tls"))

    assert_that(response.ok).is_false()


def test_exposes_channel_of_client(service_addr: str) -> None:
    """Клиент отдает канал, через который отправляет запросы."""
    with GRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        assert_that(client.channel).is_not_none()
