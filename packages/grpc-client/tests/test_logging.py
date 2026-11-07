import io
import logging
import time
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import grpc
from api import grpcbin_pb2
from grpc_client import options
from grpc_client.interceptors import LoggingInterceptor
from grpc_client.utils.logutils import PAYLOAD_UNAVAILABLE

from .assertions import assert_that
from .clients import GRPCbinServiceClient
from .fakes import FakeCallbackStreamCall, fake_call_details
from .support import code_number

if TYPE_CHECKING:
    from collections.abc import Callable


def test_logs_sent_request(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Отправленный запрос попадает в лог."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="накладная"))

    assert_that(log_stream).logged("GRPC request sent")


def test_logs_received_response(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Полученный ответ попадает в лог."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="акт сверки"))

    assert_that(log_stream).logged("GRPC response received")


def test_logs_request_payload(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Тело запроса попадает в лог."""
    payload = "инвентаризация склада"

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=payload))

    assert_that(log_stream).logged(payload)


def test_logs_error_status(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Ошибка вызова попадает в лог."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="товар не найден")

    assert_that(log_stream).logged("GRPC error occurred")


def test_logs_error_reason(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Текст ошибки от сервиса попадает в лог."""
    reason = "поставка отменена"

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.ABORTED), reason=reason)

    assert_that(log_stream).logged(reason)


def test_masks_authorization_metadata_by_default(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Заголовок авторизации маскируется в логе запроса без дополнительной настройки."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.get_headers({"authorization": "Bearer s3cr3t-token-value"})

    assert_that(log_stream).logged('"authorization": "****"')


def test_masks_nested_payload_field_by_glom_path(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Вложенное поле тела сообщения маскируется по glom-пути."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, sanitize_keys=["Metadata.authorization.values"]),
    ) as client:
        client.get_headers({"authorization": "Bearer nested-secret-value"})

    assert_that(log_stream).not_logged("nested-secret-value")


def test_masks_configured_payload_field(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Поле тела запроса, указанное в настройках, маскируется в логе."""
    secret_value = uuid4().hex
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, sanitize_keys=["fString"]),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=secret_value))

    assert_that(log_stream).not_logged(secret_value)


def test_completes_server_stream_with_logging_interceptor(
    service_addr: str,
    logger: logging.Logger,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Поток ответов работает, когда к клиенту подключено логирование."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        response = client.send_server_stream(dummy_message).collect()

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_logs_finished_server_stream(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Завершение потока ответов попадает в лог."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.send_server_stream(dummy_message).collect()

    assert_that(log_stream).logged("GRPC stream finished")


def test_logs_number_of_streamed_messages(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Количество полученных сообщений потока попадает в лог."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.send_server_stream(dummy_message).collect()

    assert_that(log_stream).logged("Messages: 10")


def test_writes_nothing_when_log_level_is_disabled(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """При отключенном уровне логирования лог остается пустым."""
    logger.setLevel(logging.CRITICAL)

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, log_level=logging.INFO, err_log_level=logging.INFO),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="тихий запрос"))

    assert_that(log_stream).has_log_records(0)


def test_truncates_long_payload(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """Слишком длинное тело сообщения обрезается в логе."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, payload_maxlength=32),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="очень длинное описание груза" * 10))

    assert_that(log_stream).logged("<обрезано>")


def test_logs_all_values_of_repeated_metadata_key(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Все значения повторяющегося ключа метаданных попадают в лог.

    Словарь оставил бы только последнее значение, и лог перестал бы соответствовать запросу.
    """
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.get_headers([("x-shard", "north"), ("x-shard", "south")])

    assert_that(log_stream).logged('"x-shard": ["north", "south"]')


def test_masks_camel_case_secret_in_payload(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Секрет в теле сообщения маскируется независимо от стиля записи имени поля."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, sanitize_keys=["f_string"]),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="секрет-в-камелькейсе"))

    assert_that(log_stream).not_logged("секрет-в-камелькейсе")


def test_sends_request_when_payload_logging_fails(
    service_addr: str,
    logger: logging.Logger,
) -> None:
    """Сбой подготовки лога не мешает отправить запрос.

    Лог запроса собирается до вызова, поэтому ошибка маскирования не должна его срывать.
    """
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, sanitize_keys=["fSub.*.fString"]),
    ) as client:
        response = client.dummy_unary(
            grpcbin_pb2.DummyMessage(
                f_string="запрос всё равно уходит",
                f_sub=grpcbin_pb2.DummyMessage.Sub(f_string="вложенное поле"),
            )
        )

    assert_that(response).has_status_code(grpc.StatusCode.OK)


def test_reports_unavailable_payload_when_logging_fails(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """При сбое подготовки тела в лог попадает явный маркер."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, sanitize_keys=["fSub.*.fString"]),
    ) as client:
        client.dummy_unary(
            grpcbin_pb2.DummyMessage(
                f_string="тело в лог не попадёт",
                f_sub=grpcbin_pb2.DummyMessage.Sub(f_string="вложенное поле"),
            )
        )

    assert_that(log_stream).logged(PAYLOAD_UNAVAILABLE)


def test_logs_finished_stream_left_unread(
    service_addr: str,
    logger: logging.Logger,
    log_stream: io.StringIO,
    dummy_message: grpcbin_pb2.DummyMessage,
) -> None:
    """Поток, который никто не дочитал, всё равно оставляет запись о завершении.

    Такой поток обрывается по deadline, и без callback самого вызова финального лога бы не было.
    """
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
        options.with_timeout(0.2),
    ) as client:
        client.send_server_stream(dummy_message)
        time.sleep(0.6)

    assert_that(log_stream).logged("GRPC error occurred")


def test_counts_message_delivered_together_with_completion(
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Сообщение попадает в счётчик, даже если вызов завершился в момент его выдачи.

    Callback завершения приходит из служебного потока grpcio и раньше мог снять счётчик
    до того, как читатель успевал учесть уже полученное сообщение.
    """
    call = FakeCallbackStreamCall(messages_count=1)
    interceptor = LoggingInterceptor(logger=logger)

    wrapped = interceptor.intercept_unary_stream(
        lambda _details, _request: call,
        fake_call_details(),
        object(),
    )
    list(wrapped)

    assert_that(log_stream).logged("Messages: 1")


def test_writes_single_final_log_for_stream(
    logger: logging.Logger,
    log_stream: io.StringIO,
) -> None:
    """Финальный лог потока записывается ровно один раз."""
    call = FakeCallbackStreamCall(messages_count=1)
    interceptor = LoggingInterceptor(logger=logger)

    wrapped = interceptor.intercept_unary_stream(
        lambda _details, _request: call,
        fake_call_details(),
        object(),
    )
    list(wrapped)
    cast("Callable[[], bool]", wrapped.cancel)()

    assert_that(log_stream.getvalue().count("GRPC stream finished")).is_equal_to(1)
