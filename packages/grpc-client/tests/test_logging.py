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
    """The sent request is logged."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="накладная"))

    assert_that(log_stream).logged("GRPC request sent")


def test_logs_received_response(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """The received response is logged."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="акт сверки"))

    assert_that(log_stream).logged("GRPC response received")


def test_logs_request_payload(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """The request body is logged."""
    payload = "инвентаризация склада"

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string=payload))

    assert_that(log_stream).logged(payload)


def test_logs_error_status(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """The call error is logged."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger),
    ) as client:
        client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="товар не найден")

    assert_that(log_stream).logged("GRPC error occurred")


def test_logs_error_reason(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """The service error text is logged."""
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
    """The authorization header is masked in request logs without additional configuration."""
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
    """A nested message body field is masked by its glom path."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, sanitize_keys=["Metadata.authorization.values"]),
    ) as client:
        client.get_headers({"authorization": "Bearer nested-secret-value"})

    assert_that(log_stream).not_logged("nested-secret-value")


def test_masks_configured_payload_field(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """A configured request body field is masked in the log."""
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
    """Response streaming works with client logging enabled."""
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
    """Response stream completion is logged."""
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
    """The number of received stream messages is logged."""
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
    """The log stays empty when its level is disabled."""
    logger.setLevel(logging.CRITICAL)

    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_logger(logger, log_level=logging.INFO, err_log_level=logging.INFO),
    ) as client:
        client.dummy_unary(grpcbin_pb2.DummyMessage(f_string="тихий запрос"))

    assert_that(log_stream).has_log_records(0)


def test_truncates_long_payload(service_addr: str, logger: logging.Logger, log_stream: io.StringIO) -> None:
    """An overly long message body is truncated in the log."""
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
    """All values of a repeated metadata key are logged.

    A dictionary would retain only the last value and make the log differ from the request.
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
    """A message body secret is masked regardless of field naming style."""
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
    """A log preparation failure does not prevent sending the request.

    Request logs are built before calling, so masking errors must not prevent the call.
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
    """A body preparation failure produces an explicit marker in the log."""
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
    """A stream left unread still produces a completion record.

    This stream ends at its deadline and would have no final log without the call callback.
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
    """A message is counted even if the call finishes while yielding it.

    The grpcio completion callback runs in an internal thread and previously could read the counter
    before the reader counted a message already received.
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
    """The final stream log is written exactly once."""
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
