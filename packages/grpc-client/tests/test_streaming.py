from collections.abc import Iterator
from typing import cast

import grpc
import pytest
from api import grpcbin_pb2
from grpc_client import (
    CallOptions,
    GRPCStreamResponse,
    StreamConsumedError,
    StreamNotConsumedError,
)

from .assertions import assert_that
from .clients import GRPCbinServiceClient
from .fakes import FakeFailingStreamCall, FakeRpcError, FakeStreamCall

STREAM_MESSAGES_COUNT = 10


def test_returns_ok_status_for_client_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """Поток запросов завершается статусом OK."""
    response = grpcbin_client.send_client_stream(dummy_messages)

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_returns_message_for_client_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """В ответ на поток запросов сервис присылает одно сообщение."""
    response = grpcbin_client.send_client_stream(dummy_messages)

    assert_that(response.message()).is_instance_of(grpcbin_pb2.DummyMessage)


def test_reads_server_stream_lazily(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Поток ответов читается по одному сообщению за раз."""
    with grpcbin_client.send_server_stream(dummy_message) as stream:
        first = next(iter(stream))

    assert_that(first).is_instance_of(grpcbin_pb2.DummyMessage)


def test_collects_all_messages_of_server_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Собранный поток ответов содержит все присланные сервисом сообщения."""
    response = grpcbin_client.send_server_stream(dummy_message).collect()

    assert_that(response.message()).is_length(STREAM_MESSAGES_COUNT)


def test_returns_ok_status_after_collecting_server_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Собранный поток ответов завершается статусом OK."""
    response = grpcbin_client.send_server_stream(dummy_message).collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_stops_collecting_server_stream_at_limit(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Сбор потока прекращается по достижении заданного предела."""
    limit = 3

    response = grpcbin_client.send_server_stream(dummy_message).collect(limit=limit)

    assert_that(response.message()).is_length(limit)


def test_collects_all_messages_of_bidirectional_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """Двунаправленный поток возвращает столько же сообщений, сколько отправлено."""
    response = grpcbin_client.send_bidirectional_stream(dummy_messages).collect()

    assert_that(response.message()).is_length(STREAM_MESSAGES_COUNT)


def test_returns_ok_status_after_collecting_bidirectional_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """Двунаправленный поток завершается статусом OK."""
    response = grpcbin_client.send_bidirectional_stream(dummy_messages).collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_reports_deadline_exceeded_for_interrupted_server_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Оборванный по истечении времени поток превращается в ответ со статусом ошибки."""
    response = grpcbin_client.send_server_stream(dummy_message, CallOptions(timeout=0.05)).collect()

    assert_that(response).has_status_code(grpc.StatusCode.DEADLINE_EXCEEDED)


def test_returns_only_messages_received_before_interruption(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Оборванный поток отдает только то, что успел прислать сервис."""
    response = grpcbin_client.send_server_stream(dummy_message, CallOptions(timeout=0.5)).collect()

    assert_that(len(response.message())).is_less_than(STREAM_MESSAGES_COUNT)


def test_rejects_second_reading_of_stream(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Повторное чтение потока завершается ошибкой."""
    stream = grpcbin_client.send_server_stream(dummy_message)
    stream.collect()

    with pytest.raises(StreamConsumedError):
        stream.collect()


def test_hides_status_until_stream_is_consumed(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Итоговый статус недоступен, пока поток не прочитан до конца."""
    with grpcbin_client.send_server_stream(dummy_message) as stream, pytest.raises(StreamNotConsumedError):
        _ = stream.status_code


def test_reports_status_after_stream_is_consumed(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """После полного чтения потока становится доступен итоговый статус."""
    stream = grpcbin_client.send_server_stream(dummy_message)
    list(stream)

    assert_that(stream.status_code).is_equal_to(grpc.StatusCode.OK)


def test_cancels_stream_on_context_exit(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Незавершенный поток отменяется при выходе из контекстного менеджера."""
    with grpcbin_client.send_server_stream(dummy_message) as stream:
        next(iter(stream))

    assert_that(stream.status_code).is_equal_to(grpc.StatusCode.CANCELLED)


def test_reads_nothing_with_zero_limit(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """С нулевым пределом поток не читается вовсе."""
    response = grpcbin_client.send_server_stream(dummy_message).collect(limit=0)

    assert_that(response.message()).is_empty()


def test_makes_no_reads_with_zero_limit() -> None:
    """С нулевым пределом сообщения у вызова не запрашиваются.

    Проверяется на поддельном вызове: по пустому списку нельзя отличить «не читали»
    от «прочитали и выбросили».
    """
    call = FakeStreamCall(messages_count=3)
    stream: GRPCStreamResponse[object] = GRPCStreamResponse(cast("grpc.Call", call))

    stream.collect(limit=0)

    assert_that(call.reads).is_equal_to(0)


def test_rejects_negative_limit(
    grpcbin_client: GRPCbinServiceClient,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Отрицательный предел числа сообщений не принимается."""
    stream = grpcbin_client.send_server_stream(dummy_message)

    with pytest.raises(ValueError, match="отрицательным"):
        stream.collect(limit=-1)


def test_keeps_messages_received_before_error() -> None:
    """Сообщения, пришедшие до ошибки сервера, остаются в собранном ответе.

    По ним видно, на каком месте оборвался поток, поэтому терять их нельзя.
    """
    received = object()
    call = FakeFailingStreamCall([received], FakeRpcError())
    stream: GRPCStreamResponse[object] = GRPCStreamResponse(cast("grpc.Call", call))

    response = stream.collect()

    assert_that(response.message()).is_equal_to([received])


def test_reports_error_status_for_interrupted_stream() -> None:
    """Оборванный поток сообщает код ошибки сервера."""
    call = FakeFailingStreamCall([object()], FakeRpcError(code=grpc.StatusCode.INTERNAL))
    stream: GRPCStreamResponse[object] = GRPCStreamResponse(cast("grpc.Call", call))

    response = stream.collect()

    assert_that(response).has_status_code(grpc.StatusCode.INTERNAL)
