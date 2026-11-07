import io
import logging
from collections.abc import Iterator
from typing import cast
from uuid import uuid4

import grpc
import pytest
from api import grpcbin_pb2
from grpc_client import LogFormat, TextLogSink, options, resolve_log_levels
from grpc_client.interceptors import LoggingInterceptor

from .assertions import assert_that
from .clients import AsyncGRPCbinServiceClient, GRPCbinServiceClient
from .fakes import FailingLogSink, FakeLogSink
from .support import code_number

STREAM_MESSAGES_COUNT = 10


@pytest.fixture()
def sink() -> FakeLogSink:
    """Приемник записей, доступный тесту для проверок."""
    return FakeLogSink()


def test_passes_sent_request_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Отправленный запрос доходит до приемника."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="накладная"))

    assert_that(sink.requests).is_length(1)


def test_passes_called_method_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Полное имя вызванного метода доходит до приемника."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="путевой лист"))

    assert_that(sink.requests[0].method).is_equal_to("/grpcbin.GRPCBin/DummyUnary")


def test_passes_sent_message_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Приемник получает то самое сообщение, которое ушло сервису."""
    message = grpcbin_pb2.DummyMessage(f_string="инвентаризация склада")

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.dummy_unary(message)

    assert_that(sink.requests[0].message).is_same_as(message)


def test_binds_request_and_response_by_one_trace_id(service_addr: str, sink: FakeLogSink) -> None:
    """Запрос и ответ приходят приемнику с одним идентификатором."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="сверка остатков"))

    assert_that(sink.responses[0].trace_id).is_equal_to(sink.requests[0].trace_id)


def test_reports_successful_call_as_succeeded(service_addr: str, sink: FakeLogSink) -> None:
    """Успешный вызов помечается в записи как успешный."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.empty()

    assert_that(sink.responses[0].succeeded).is_true()


def test_reports_unary_call_as_not_streamed(service_addr: str, sink: FakeLogSink) -> None:
    """Унарный вызов не помечается как потоковый."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.empty()

    assert_that(sink.responses[0].is_stream).is_false()


def test_passes_received_message_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Ответное сообщение доходит до приемника."""
    payload = "акт приема-передачи"

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=payload))

    received = cast("grpcbin_pb2.DummyMessage", sink.responses[0].message)
    assert_that(received.f_string).is_equal_to(payload)


def test_writes_successful_call_with_success_level(service_addr: str, sink: FakeLogSink) -> None:
    """Успешный вызов записывается уровнем успешных запросов."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink, log_level=logging.DEBUG),
    ) as client:
        client.empty()

    assert_that(sink.response_levels).is_equal_to([logging.DEBUG])


def test_writes_failed_call_with_error_level(service_addr: str, sink: FakeLogSink) -> None:
    """Вызов с ошибкой записывается уровнем ошибок."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink, err_log_level=logging.WARNING),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="паллета не найдена")

    assert_that(sink.response_levels).is_equal_to([logging.WARNING])


def test_reports_failed_call_as_not_succeeded(service_addr: str, sink: FakeLogSink) -> None:
    """Вызов с ошибкой помечается в записи как неуспешный."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.ABORTED), reason="отгрузка отменена")

    assert_that(sink.responses[0].succeeded).is_false()


def test_passes_error_status_code_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Код ошибки доходит до приемника."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.PERMISSION_DENIED), reason="нет доступа к складу")

    assert_that(sink.responses[0].status_code).is_equal_to(grpc.StatusCode.PERMISSION_DENIED)


def test_passes_error_details_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Текст ошибки от сервиса доходит до приемника."""
    reason = "поставка отменена"

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.FAILED_PRECONDITION), reason=reason)

    assert_that(sink.responses[0].details).is_equal_to(reason)


def test_leaves_message_empty_for_failed_call(service_addr: str, sink: FakeLogSink) -> None:
    """У вызова с ошибкой ответного сообщения в записи нет."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.UNAVAILABLE), reason="склад недоступен")

    assert_that(sink.responses[0].message).is_none()


def test_leaves_details_empty_for_successful_call(service_addr: str, sink: FakeLogSink) -> None:
    """У успешного вызова текста ошибки в записи нет."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.empty()

    assert_that(sink.responses[0].details).is_empty()


def test_reports_finished_stream_as_streamed(
    service_addr: str,
    sink: FakeLogSink,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Завершившийся поток ответов помечается в записи как потоковый."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.send_server_stream(dummy_message).collect()

    assert_that(sink.responses[0].is_stream).is_true()


def test_passes_streamed_messages_count_to_sink(
    service_addr: str,
    sink: FakeLogSink,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Количество полученных сообщений потока доходит до приемника."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.send_server_stream(dummy_message).collect()

    assert_that(sink.responses[0].messages_count).is_equal_to(STREAM_MESSAGES_COUNT)


def test_leaves_message_empty_for_finished_stream(
    service_addr: str,
    sink: FakeLogSink,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """У завершившегося потока ответного сообщения в записи нет."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.send_server_stream(dummy_message).collect()

    assert_that(sink.responses[0].message).is_none()


def test_leaves_message_empty_for_client_stream_request(
    service_addr: str,
    sink: FakeLogSink,
    dummy_messages: Iterator[grpcbin_pb2.DummyMessage],
) -> None:
    """У запроса, телом которого был поток, сообщения в записи нет."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        client.send_client_stream(dummy_messages)

    assert_that(sink.requests[0].message).is_none()


def test_skips_request_when_sink_disables_every_level(service_addr: str) -> None:
    """При выключенных уровнях запись запроса приемнику не отдается."""
    silent_sink = FakeLogSink(enabled_levels=())

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(silent_sink),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="тихая отгрузка"))

    assert_that(silent_sink.requests).is_empty()


def test_skips_response_when_sink_disables_every_level(service_addr: str) -> None:
    """При выключенных уровнях запись об исходе приемнику не отдается."""
    silent_sink = FakeLogSink(enabled_levels=())

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(silent_sink),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="тихая приемка"))

    assert_that(silent_sink.responses).is_empty()


def test_writes_response_when_only_error_level_is_enabled(service_addr: str) -> None:
    """Выключенный уровень успешных запросов не мешает записать ошибку."""
    error_only_sink = FakeLogSink(enabled_levels=(logging.ERROR,))

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(error_only_sink),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.INTERNAL), reason="сбой на складе")

    assert_that(error_only_sink.responses).is_length(1)


def test_completes_call_when_sink_fails_to_write(service_addr: str) -> None:
    """Сбой приемника не мешает выполнить вызов."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(FailingLogSink()),
    ) as client:
        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="запрос всё равно уходит"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_completes_call_when_sink_fails_to_check_level(service_addr: str) -> None:
    """Сбой приемника на проверке уровня не мешает выполнить вызов."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(FailingLogSink(fail_on_check=True)),
    ) as client:
        response = client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="уровень не спросили"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_completes_server_stream_when_sink_fails(
    service_addr: str,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Сбой приемника не мешает дочитать поток ответов."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(FailingLogSink()),
    ) as client:
        response = client.send_server_stream(dummy_message).collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_rejects_both_logger_and_sink(logger: logging.Logger) -> None:
    """Интерцептор не принимает логгер и приемник одновременно."""
    with pytest.raises(TypeError):
        LoggingInterceptor(logger=logger, sink=FakeLogSink())


def test_rejects_neither_logger_nor_sink() -> None:
    """Интерцептор не собирается без логгера и без приемника."""
    with pytest.raises(TypeError):
        LoggingInterceptor()


def test_writes_text_through_built_in_sink(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Встроенный текстовый приемник пишет тот же лог, что и `with_logger`."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(TextLogSink(logger)),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="товарная накладная"))

    assert_that(log_stream).logged("GRPC request sent")


def test_masks_secrets_in_built_in_sink_by_default(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Встроенный приемник маскирует типовые секреты без дополнительной настройки."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(TextLogSink(logger)),
    ) as client:
        client.get_headers({"authorization": "Bearer w4rehouse-s3cret"})

    assert_that(log_stream).not_logged("w4rehouse-s3cret")


def test_applies_given_format_in_built_in_sink(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Приемник оформляет лог по переданным ему правилам, а не по общим."""
    secret_value = uuid4().hex
    log_format = LogFormat.from_config(sanitize_keys=["fString"])

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(TextLogSink(logger, log_format)),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=secret_value))

    assert_that(log_stream).not_logged(secret_value)


def test_adds_default_secrets_to_given_sanitize_keys() -> None:
    """`LogFormat.from_config` дополняет заданные ключи типовыми секретами."""
    log_format = LogFormat.from_config(sanitize_keys=["warehouse_pin"])

    assert_that(log_format.sanitize_keys).contains("warehouse_pin", "authorization")


def test_keeps_only_given_sanitize_keys_when_defaults_are_off() -> None:
    """С выключенными типовыми секретами остаются только заданные ключи."""
    log_format = LogFormat.from_config(sanitize_keys=["pallet_code"], use_default_sanitize_keys=False)

    assert_that(log_format.sanitize_keys).is_equal_to(("pallet_code",))


def test_keeps_given_payload_maxlength() -> None:
    """Заданная длина тела сообщения не подменяется значением из конфигурации."""
    maxlength = 64

    log_format = LogFormat.from_config(payload_maxlength=maxlength)

    assert_that(log_format.payload_maxlength).is_equal_to(maxlength)


def test_keeps_given_log_levels() -> None:
    """`resolve_log_levels` оставляет заданные уровни без изменений."""
    levels = (logging.DEBUG, logging.CRITICAL)

    assert_that(resolve_log_levels(*levels)).is_equal_to(levels)


async def test_passes_async_response_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Исход асинхронного вызова доходит до приемника."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="транспортная накладная"))

    assert_that(sink.responses).is_length(1)


async def test_passes_async_received_message_to_sink(service_addr: str, sink: FakeLogSink) -> None:
    """Ответное сообщение асинхронного вызова доходит до приемника."""
    payload = "маршрутный лист"

    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=payload))

    received = cast("grpcbin_pb2.DummyMessage", sink.responses[0].message)
    assert_that(received.f_string).is_equal_to(payload)


async def test_writes_failed_async_call_with_error_level(service_addr: str, sink: FakeLogSink) -> None:
    """Асинхронный вызов с ошибкой записывается уровнем ошибок."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink, err_log_level=logging.WARNING),
    ) as client:
        await client.specific_error(code=code_number(grpc.StatusCode.DATA_LOSS), reason="партия потеряна")

    assert_that(sink.response_levels).is_equal_to([logging.WARNING])


async def test_passes_async_streamed_messages_count_to_sink(
    service_addr: str,
    sink: FakeLogSink,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Количество сообщений асинхронного потока доходит до приемника."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(sink),
    ) as client:
        stream = await client.send_server_stream(dummy_message)
        await stream.collect()

    assert_that(sink.responses[0].messages_count).is_equal_to(STREAM_MESSAGES_COUNT)


async def test_completes_async_call_when_sink_fails(service_addr: str) -> None:
    """Сбой приемника не мешает выполнить асинхронный вызов."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(FailingLogSink()),
    ) as client:
        response = await client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="асинхронная отгрузка"))

    assert_that(response).has_status_code(grpc.StatusCode.OK)


async def test_completes_async_stream_when_sink_fails(
    service_addr: str,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Сбой приемника не мешает дочитать асинхронный поток ответов."""
    async with AsyncGRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_log_sink(FailingLogSink()),
    ) as client:
        stream = await client.send_server_stream(dummy_message)
        response = await stream.collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)
