import logging
from uuid import uuid4

import grpc
import pytest
from grpc_client.utils.logutils import PAYLOAD_UNAVAILABLE
from grpc_client_structlog import with_structlogger
from grpc_client_structlog.parser import STREAMED_CONTENT

from .assertions import assert_that
from .conftest import BuildAsyncClient, BuildClient
from .fakes import (
    StructlogRecorder,
    build_filtering_logger,
    build_logger_with_broken_level_check,
    build_stdlib_logger,
)
from .service import (
    TRAILING_METADATA_KEY,
    UNARY_METHOD,
    build_failing_message,
    build_message,
    build_message_with_trailing_metadata,
)


def test_names_the_request_event(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(invoice="A-19"))

    assert_that(logger.entries[0]).has_event("grpc request sent")


def test_names_the_response_event(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(waybill="F-77"))

    assert_that(logger.entries[1]).has_event("grpc response received")


def test_logs_the_called_method(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(warehouse="Пермь"))

    assert_that(logger.request).has_method(UNARY_METHOD)


def test_logs_the_request_body(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(sku="A-19", quantity=3))

    assert_that(logger.request).has_body_field("sku", "A-19")


def test_gives_the_request_a_trace_id(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(audit="events"))

    assert_that(logger.request).has_trace_id()


def test_links_the_response_to_its_request(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(ledger="2024"))

    assert_that(logger.response).has_same_trace_id_as(logger.request)


def test_logs_the_response_status_code(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(shipment="ready"))

    assert_that(logger.response).has_status_code(grpc.StatusCode.OK.name)


def test_logs_the_response_body(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_answer = 42
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(answer=expected_answer))

    assert_that(logger.response).has_body_field("answer", expected_answer)


def test_logs_a_metadataless_request_without_extra_fields(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(forecast="sunny"))

    assert_that(logger.request).has_fields("method", "body", "trace_id")


def test_keeps_the_message_field_out_of_the_request(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(parcel="P-8"))

    assert_that(logger.request).has_no_field("message")


def test_keeps_the_message_field_out_of_the_response(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(parcel="P-9"))

    assert_that(logger.response).has_no_field("message")


def test_logs_the_error_status_code(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_code = grpc.StatusCode.NOT_FOUND
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_failing_message(expected_code, "товар не найден"))

    assert_that(logger.response).has_status_code(expected_code.name)


def test_logs_the_error_details(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_reason = "поставка отменена"
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_failing_message(grpc.StatusCode.ABORTED, expected_reason))

    assert_that(logger.response).has_details(expected_reason)


def test_keeps_the_body_out_of_the_error_record(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_failing_message(grpc.StatusCode.PERMISSION_DENIED, "склад закрыт"))

    assert_that(logger.response).has_no_field("body")


def test_writes_a_successful_call_at_the_info_level(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(pallet=7))

    assert_that(logger.response).has_level(logging.INFO)


def test_writes_a_failed_call_at_the_error_level(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_failing_message(grpc.StatusCode.UNAVAILABLE, "сервис недоступен"))

    assert_that(logger.response).has_level(logging.ERROR)


def test_uses_the_log_level_given_to_the_option(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger, log_level=logging.DEBUG))

    client.echo(build_message(health="ok"))

    assert_that(logger.request).has_level(logging.DEBUG)


def test_uses_the_err_log_level_given_to_the_option(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger, err_log_level=logging.WARNING))

    client.echo(build_failing_message(grpc.StatusCode.DATA_LOSS, "данные потеряны"))

    assert_that(logger.response).has_level(logging.WARNING)


def test_rejects_a_log_level_structlog_cannot_write(logger: StructlogRecorder, build_client: BuildClient) -> None:
    unsupported_level = 15

    with pytest.raises(ValueError, match="log_level"):
        build_client(with_structlogger(logger.logger, log_level=unsupported_level))


def test_rejects_an_err_log_level_structlog_cannot_write(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    unsupported_level = 45

    with pytest.raises(ValueError, match="err_log_level"):
        build_client(with_structlogger(logger.logger, err_log_level=unsupported_level))


@pytest.mark.usefixtures("unsupported_global_log_level")
def test_rejects_a_log_level_taken_from_the_global_configuration(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    with pytest.raises(ValueError, match="log_level"):
        build_client(with_structlogger(logger.logger))


def test_logs_the_request_metadata(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_shard = "north"
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(order=11), {"x-shard": expected_shard})

    assert_that(logger.request).has_metadata_value("x-shard", expected_shard)


def test_logs_every_value_of_a_repeated_metadata_key(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_regions = ["ural", "siberia"]
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(order=12), [("x-region", region) for region in expected_regions])

    assert_that(logger.request).has_metadata_value("x-region", expected_regions)


def test_logs_the_response_metadata(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_value = "shelf-3"
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message_with_trailing_metadata(expected_value))

    assert_that(logger.response).has_metadata_value(TRAILING_METADATA_KEY, expected_value)


def test_masks_the_authorization_metadata_by_default(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(vault="keys"), {"authorization": "Bearer nWq7dLp2"})

    assert_that(logger.request).has_masked_metadata_value("authorization")


def test_keeps_the_authorization_value_out_of_the_log(logger: StructlogRecorder, build_client: BuildClient) -> None:
    credentials = "Bearer 8xKm2pQ"
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(vault="secrets"), {"authorization": credentials})

    assert_that(logger.request).does_not_expose(credentials)


def test_masks_the_metadata_key_it_was_asked_to_mask(logger: StructlogRecorder, build_client: BuildClient) -> None:
    tenant_key = "tnt-4417"
    client = build_client(with_structlogger(logger.logger, sanitize_keys=["x-tenant-key"]))

    client.echo(build_message(tenant="acme"), {"x-tenant-key": tenant_key})

    assert_that(logger.request).does_not_expose(tenant_key)


def test_masks_a_password_in_the_body_by_default(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(login="morgan", password=uuid4().hex))

    assert_that(logger.request).has_masked_body_field("password")


def test_keeps_ordinary_body_fields_readable(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_login = "morgan"
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(login=expected_login, password=uuid4().hex))

    assert_that(logger.request).has_body_field("login", expected_login)


def test_masks_a_nested_secret_by_default(logger: StructlogRecorder, build_client: BuildClient) -> None:
    nested_secret = uuid4().hex
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(user={"profile": {"password": nested_secret}}))

    assert_that(logger.request).does_not_expose(nested_secret)


def test_masks_the_body_field_it_was_asked_to_mask(logger: StructlogRecorder, build_client: BuildClient) -> None:
    phone = "+7 900 000-00-00"
    client = build_client(with_structlogger(logger.logger, sanitize_keys=["contact.phone"]))

    client.echo(build_message(contact={"phone": phone, "city": "Выборг"}))

    assert_that(logger.request).does_not_expose(phone)


def test_keeps_masking_typical_secrets_alongside_custom_keys(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    client = build_client(with_structlogger(logger.logger, sanitize_keys=["contact.phone"]))

    client.echo(build_message(contact={"phone": "+7 812 000-00-00"}, api_key="ak-3319"))

    assert_that(logger.request).has_masked_body_field("api_key")


def test_masks_a_camel_case_secret_by_default(logger: StructlogRecorder, build_client: BuildClient) -> None:
    camel_case_secret = uuid4().hex
    client = build_client(with_structlogger(logger.logger))

    client.echo(build_message(accessToken=camel_case_secret))

    assert_that(logger.request).does_not_expose(camel_case_secret)


def test_keeps_secrets_readable_when_default_masking_is_off(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    plain_secret = uuid4().hex
    client = build_client(with_structlogger(logger.logger, use_default_sanitize_keys=False))

    client.echo(build_message(token=plain_secret))

    assert_that(logger.request).has_body_field("token", plain_secret)


def test_reports_a_body_it_cannot_prepare(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger, sanitize_keys=["attachment.*.scan"]))

    client.echo(build_message(attachment={"scan": "страница 1"}))

    assert_that(logger.request).has_body(PAYLOAD_UNAVAILABLE)


def test_sends_the_request_when_body_logging_fails(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger, sanitize_keys=["attachment.*.scan"]))

    response = client.echo(build_message(attachment={"scan": "страница 2"}))

    assert_that(response.status_code).is_equal_to(grpc.StatusCode.OK)


def test_keeps_the_response_message_readable(logger: StructlogRecorder, build_client: BuildClient) -> None:
    real_password = uuid4().hex
    client = build_client(with_structlogger(logger.logger))

    response = client.echo(build_message(password=real_password))

    assert_that(dict(response.message().items())).is_equal_to({"password": real_password})


def test_indents_the_body_as_requested(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger, json_indent=4))

    client.echo(build_message(shape="circle"))

    assert_that(logger.request).has_body('{\n    "shape": "circle"\n}')


def test_truncates_a_body_longer_than_asked(logger: StructlogRecorder, build_client: BuildClient) -> None:
    maxlength = 32
    client = build_client(with_structlogger(logger.logger, payload_maxlength=maxlength))

    client.echo(build_message(cargo="контейнер " * 20))

    assert_that(logger.request).has_truncated_body(maxlength)


def test_keeps_a_body_shorter_than_the_limit_whole(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger, payload_maxlength=128))

    client.echo(build_message(cargo="ящик"))

    assert_that(logger.request).has_body('{"cargo": "ящик"}')


def test_marks_a_client_stream_request_body_as_a_stream(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.upload(iter([build_message(crate=1), build_message(crate=2)]))

    assert_that(logger.request).has_body(STREAMED_CONTENT)


def test_logs_the_response_body_of_a_client_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    crates = [build_message(crate=index) for index in range(4)]
    client = build_client(with_structlogger(logger.logger))

    client.upload(iter(crates))

    assert_that(logger.response).has_body_field("received", len(crates))


def test_logs_the_status_code_of_a_client_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.upload(iter([build_message(box="B-1")]))

    assert_that(logger.response).has_status_code(grpc.StatusCode.OK.name)


def test_counts_the_messages_of_a_server_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_length = 5
    client = build_client(with_structlogger(logger.logger))

    client.download(build_message(stream_length=expected_length)).collect()

    assert_that(logger.response).has_messages_count(expected_length)


def test_keeps_the_body_out_of_a_server_stream_record(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.download(build_message(catalog="tools")).collect()

    assert_that(logger.response).has_no_field("body")


def test_logs_the_status_code_of_a_server_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.download(build_message(catalog="boots")).collect()

    assert_that(logger.response).has_status_code(grpc.StatusCode.OK.name)


def test_counts_the_messages_of_a_bidirectional_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    letters = [build_message(letter=letter) for letter in ("alpha", "bravo", "charlie")]
    client = build_client(with_structlogger(logger.logger))

    client.chat(iter(letters)).collect()

    assert_that(logger.response).has_messages_count(len(letters))


def test_logs_the_status_code_of_a_failed_server_stream(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    expected_code = grpc.StatusCode.RESOURCE_EXHAUSTED
    client = build_client(with_structlogger(logger.logger))

    client.download(build_failing_message(expected_code, "квота исчерпана")).collect()

    assert_that(logger.response).has_status_code(expected_code.name)


def test_logs_the_details_of_a_failed_server_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    expected_reason = "лента оборвалась"
    client = build_client(with_structlogger(logger.logger))

    client.download(build_failing_message(grpc.StatusCode.INTERNAL, expected_reason)).collect()

    assert_that(logger.response).has_details(expected_reason)


def test_counts_the_messages_of_a_failed_server_stream(logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.download(build_failing_message(grpc.StatusCode.UNAVAILABLE, "стеллаж недоступен")).collect()

    assert_that(logger.response).has_messages_count(0)


def test_writes_a_failed_server_stream_at_the_error_level(
    logger: StructlogRecorder,
    build_client: BuildClient,
) -> None:
    client = build_client(with_structlogger(logger.logger))

    client.download(build_failing_message(grpc.StatusCode.ABORTED, "инвентаризация")).collect()

    assert_that(logger.response).has_level(logging.ERROR)


def test_logs_through_a_filtering_bound_logger(filtering_logger: StructlogRecorder, build_client: BuildClient) -> None:
    client = build_client(with_structlogger(filtering_logger.logger))

    client.echo(build_message(regression="is_enabled_for"))

    assert_that(filtering_logger.request).has_method(UNARY_METHOD)


def test_writes_nothing_when_the_filtering_logger_drops_every_level(build_client: BuildClient) -> None:
    quiet_logger = build_filtering_logger(logging.CRITICAL)
    client = build_client(with_structlogger(quiet_logger.logger))

    client.echo(build_message(silence="golden"))

    assert_that(quiet_logger.entries).is_empty()


def test_writes_nothing_when_the_stdlib_logger_drops_every_level(build_client: BuildClient) -> None:
    quiet_logger = build_stdlib_logger(logging.CRITICAL)
    client = build_client(with_structlogger(quiet_logger.logger))

    client.echo(build_message(silence="platinum"))

    assert_that(quiet_logger.entries).is_empty()


def test_sends_the_request_when_the_level_check_fails(build_client: BuildClient) -> None:
    broken_logger = build_logger_with_broken_level_check()
    client = build_client(with_structlogger(broken_logger.logger))

    response = client.echo(build_message(fallback="enabled"))

    assert_that(response.status_code).is_equal_to(grpc.StatusCode.OK)


def test_logs_the_request_when_the_level_check_fails(build_client: BuildClient) -> None:
    broken_logger = build_logger_with_broken_level_check()
    client = build_client(with_structlogger(broken_logger.logger))

    client.echo(build_message(fallback="logged"))

    assert_that(broken_logger.request).has_method(UNARY_METHOD)


@pytest.mark.asyncio
async def test_logs_a_request_of_an_async_client(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    client = build_async_client(with_structlogger(logger.logger))

    await client.echo(build_message(tick=8))

    assert_that(logger.request).has_body_field("tick", 8)


@pytest.mark.asyncio
async def test_logs_a_response_of_an_async_client(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    client = build_async_client(with_structlogger(logger.logger))

    await client.echo(build_message(tock=9))

    assert_that(logger.response).has_body_field("tock", 9)


@pytest.mark.asyncio
async def test_logs_an_error_status_code_of_an_async_client(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    expected_code = grpc.StatusCode.FAILED_PRECONDITION
    client = build_async_client(with_structlogger(logger.logger))

    await client.echo(build_failing_message(expected_code, "склад не подготовлен"))

    assert_that(logger.response).has_status_code(expected_code.name)


@pytest.mark.asyncio
async def test_masks_a_secret_of_an_async_client(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    session_secret = uuid4().hex
    client = build_async_client(with_structlogger(logger.logger))

    await client.echo(build_message(access_token=session_secret))

    assert_that(logger.request).does_not_expose(session_secret)


@pytest.mark.asyncio
async def test_logs_through_a_filtering_bound_logger_in_an_async_client(
    filtering_logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    client = build_async_client(with_structlogger(filtering_logger.logger))

    await client.echo(build_message(regression="async"))

    assert_that(filtering_logger.request).has_method(UNARY_METHOD)


@pytest.mark.asyncio
async def test_marks_an_async_client_stream_request_body_as_a_stream(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    client = build_async_client(with_structlogger(logger.logger))

    await client.upload(iter([build_message(barrel=1), build_message(barrel=2)]))

    assert_that(logger.request).has_body(STREAMED_CONTENT)


@pytest.mark.asyncio
async def test_counts_the_messages_of_an_async_server_stream(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    expected_length = 6
    client = build_async_client(with_structlogger(logger.logger))

    async with client:
        stream = await client.download(build_message(stream_length=expected_length))
        await stream.collect()

    assert_that(logger.response).has_messages_count(expected_length)


@pytest.mark.asyncio
async def test_counts_the_messages_of_an_async_bidirectional_stream(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    signals = [build_message(signal=signal) for signal in ("ping", "pong")]
    client = build_async_client(with_structlogger(logger.logger))

    async with client:
        stream = await client.chat(iter(signals))
        await stream.collect()

    assert_that(logger.response).has_messages_count(len(signals))


@pytest.mark.asyncio
async def test_logs_the_status_code_of_a_failed_async_server_stream(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    expected_code = grpc.StatusCode.RESOURCE_EXHAUSTED
    client = build_async_client(with_structlogger(logger.logger))

    async with client:
        stream = await client.download(build_failing_message(expected_code, "квота исчерпана"))
        await stream.collect()

    assert_that(logger.response).has_status_code(expected_code.name)


@pytest.mark.asyncio
async def test_writes_a_failed_async_server_stream_at_the_error_level(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    client = build_async_client(with_structlogger(logger.logger))

    async with client:
        stream = await client.download(build_failing_message(grpc.StatusCode.INTERNAL, "лента оборвалась"))
        await stream.collect()

    assert_that(logger.response).has_level(logging.ERROR)


@pytest.mark.asyncio
async def test_logs_the_response_metadata_of_an_async_client(
    logger: StructlogRecorder,
    build_async_client: BuildAsyncClient,
) -> None:
    expected_value = "rack-9"
    client = build_async_client(with_structlogger(logger.logger))

    await client.echo(build_message_with_trailing_metadata(expected_value))

    assert_that(logger.response).has_metadata_value(TRAILING_METADATA_KEY, expected_value)


@pytest.mark.asyncio
async def test_sends_the_request_of_an_async_client_when_the_level_check_fails(
    build_async_client: BuildAsyncClient,
) -> None:
    broken_logger = build_logger_with_broken_level_check()
    client = build_async_client(with_structlogger(broken_logger.logger))

    response = await client.echo(build_message(fallback="async"))

    assert_that(response.status_code).is_equal_to(grpc.StatusCode.OK)
