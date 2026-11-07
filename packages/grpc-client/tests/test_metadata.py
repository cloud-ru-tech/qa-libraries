import grpc
from grpc_client import CallOptions, Metadata, options

from .assertions import assert_that
from .clients import GRPCbinServiceClient
from .support import code_number


def test_sends_metadata_from_dict(grpcbin_client: GRPCbinServiceClient) -> None:
    """Метаданные, переданные словарем, доходят до сервиса."""
    response = grpcbin_client.get_headers({"x-order-id": "A-1024"})

    assert_that(response).received_metadata("x-order-id", "A-1024")


def test_sends_binary_metadata(grpcbin_client: GRPCbinServiceClient) -> None:
    """Двоичные метаданные доходят до сервиса."""
    response = grpcbin_client.get_headers({"x-payload-bin": b"raw-bytes"})

    assert_that(response).received_metadata("x-payload-bin", "raw-bytes")


def test_sends_repeated_metadata_keys(grpcbin_client: GRPCbinServiceClient) -> None:
    """Повторяющиеся ключи метаданных доходят до сервиса все.

    Так сервисы передают, например, несколько меток эксперимента в одном запросе.
    """
    response = grpcbin_client.get_headers([("x-feature", "search"), ("x-feature", "ranking")])

    assert_that(response).received_all_metadata("x-feature", ["search", "ranking"])


def test_sends_default_metadata_of_client(service_addr: str) -> None:
    """Метаданные клиента добавляются к каждому запросу."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_default_metadata({"x-tenant": "warehouse-42"}),
    ) as client:
        response = client.get_headers()

    assert_that(response).received_metadata("x-tenant", "warehouse-42")


def test_sends_request_metadata_together_with_default(service_addr: str) -> None:
    """Метаданные запроса не вытесняют метаданные клиента."""
    with GRPCbinServiceClient.from_addr(
        service_addr,
        options.with_insecure_channel(),
        options.with_default_metadata({"x-tenant": "warehouse-7"}),
    ) as client:
        response = client.get_headers({"x-trace": "abc"})

    assert_that(response).received_metadata("x-tenant", "warehouse-7")


def test_sends_metadata_from_call_options(grpcbin_client: GRPCbinServiceClient) -> None:
    """Метаданные из параметров вызова доходят до сервиса."""
    response = grpcbin_client.get_headers(options=CallOptions(metadata={"x-attempt": "2"}))

    assert_that(response).received_metadata("x-attempt", "2")


def test_returns_trailing_metadata_of_response(grpcbin_client: GRPCbinServiceClient) -> None:
    """Ответ содержит trailing-метаданные сервиса."""
    response = grpcbin_client.specific_error(code=code_number(grpc.StatusCode.NOT_FOUND), reason="нет такого")

    assert_that(response.trailing_metadata).is_instance_of(Metadata)


def test_keeps_all_values_of_repeated_metadata_key() -> None:
    """Метаданные сохраняют все значения повторяющегося ключа."""
    metadata = Metadata([("x-label", "alpha"), ("x-label", "beta")])

    assert_that(metadata.get_all("x-label")).is_equal_to(("alpha", "beta"))


def test_reads_metadata_key_ignoring_case() -> None:
    """Ключ метаданных читается независимо от регистра."""
    metadata = Metadata([("X-Request-Id", "42")])

    assert_that(metadata["x-request-id"]).is_equal_to("42")


def test_returns_first_value_of_repeated_metadata_key() -> None:
    """По ключу с повторами метаданные отдают первое значение."""
    metadata = Metadata([("x-shard", "one"), ("x-shard", "two")])

    assert_that(metadata["x-shard"]).is_equal_to("one")


def test_counts_repeated_metadata_key_once() -> None:
    """Повторяющийся ключ считается одним при подсчете размера."""
    metadata = Metadata([("x-zone", "eu"), ("x-zone", "us"), ("x-region", "north")])

    assert_that(len(metadata)).is_equal_to(2)
