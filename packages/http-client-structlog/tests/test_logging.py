import logging
from collections.abc import AsyncIterator, Generator, Iterator
from typing import TYPE_CHECKING, Protocol, cast

import httpx
import pytest
from http_client import AsyncHttpClient, ClientOption, HttpClient
from http_client.config import DEFAULT_OCTET_STREAM_LOG_MAXLENGTH, LoggingConfig, configure_logging
from http_client.options import with_auth
from http_client_structlog import with_structlogger
from pytest_httpx import HTTPXMock

from .assertions import assert_that
from .fakes import FakeStructLogger

if TYPE_CHECKING:
    from .json_types import JsonValue


class BuildClient(Protocol):
    def __call__(self, base_url: str, *options: ClientOption) -> HttpClient: ...


class BuildAsyncClient(Protocol):
    def __call__(self, base_url: str, *options: ClientOption) -> AsyncHttpClient: ...


class RetryingAuth(httpx.Auth):
    """Retry the request with a fresh token after a 401."""

    def __init__(self) -> None:
        """Create an instance with the supplied settings."""
        self.retried = False

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        response = yield request

        if response.status_code == httpx.codes.UNAUTHORIZED and not self.retried:
            self.retried = True
            request.headers["Authorization"] = "Bearer refreshed-token"
            response = yield request

        return


@pytest.fixture(autouse=True)
def reset_logging_config() -> Iterator[None]:
    configure_logging()
    yield
    configure_logging()


@pytest.fixture()
def logger() -> FakeStructLogger:
    return FakeStructLogger()


@pytest.fixture()
def build_client() -> Iterator[BuildClient]:
    clients: list[HttpClient] = []

    def build(base_url: str, *options: ClientOption) -> HttpClient:
        client = HttpClient(base_url, *options)
        clients.append(client)
        return client

    yield build

    for client in clients:
        client.close()


@pytest.fixture()
async def build_async_client() -> AsyncIterator[BuildAsyncClient]:
    clients: list[AsyncHttpClient] = []

    def build(base_url: str, *options: ClientOption) -> AsyncHttpClient:
        client = AsyncHttpClient(base_url, *options)
        clients.append(client)
        return client

    yield build

    for client in clients:
        await client.aclose()


def test_names_the_request_event(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://shop.test", with_structlogger(logger))

    client.get("/catalog")

    assert_that(logger.entries[0]).has_event("http request sent")


def test_names_the_response_event(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://shop.test", with_structlogger(logger))

    client.get("/catalog")

    assert_that(logger.entries[1]).has_event("http response received")


def test_logs_the_request_method(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=204)
    client = build_client("https://tasks.test", with_structlogger(logger))

    client.delete("/tasks/17")

    assert_that(logger.request).has_method("DELETE")


def test_logs_the_request_url(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://billing.test", with_structlogger(logger))

    client.get("/invoices/2024")

    assert_that(logger.request).has_url("https://billing.test/invoices/2024")


def test_logs_a_bodiless_request_without_extra_fields(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://weather.test", with_structlogger(logger))

    client.get("/forecast")

    assert_that(logger.request).has_fields("method", "url", "headers", "trace_id")


def test_logs_the_request_query_params(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://search.test", with_structlogger(logger))

    client.get("/items", params={"category": "boots"})

    assert_that(logger.request).has_query_param("category", "boots")


def test_logs_the_request_json_body(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=201)
    client = build_client("https://orders.test", with_structlogger(logger))

    json_payload_1: dict[str, JsonValue] = {"sku": "A-19", "quantity": 3}
    client.post("/orders", json=json_payload_1)

    assert_that(logger.request).has_body_field("sku", "A-19")


def test_gives_the_request_a_trace_id(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://audit.test", with_structlogger(logger))

    client.get("/events")

    assert_that(logger.request).has_trace_id()


def test_links_the_response_to_its_request(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://audit.test", with_structlogger(logger))

    client.get("/events")

    assert_that(logger.response).has_same_trace_id_as(logger.request)


def test_logs_the_response_status_code(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=202)
    client = build_client("https://jobs.test", with_structlogger(logger))

    client.post("/jobs")

    assert_that(logger.response).has_status_code(202)


def test_logs_the_response_json_body(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_2: dict[str, JsonValue] = {"name": "Deep Thought", "answer": 42}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_2,
    )
    client = build_client("https://oracle.test", with_structlogger(logger))

    client.get("/question")

    assert_that(logger.response).has_body_field("answer", 42)


def test_logs_the_response_headers(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    json_payload_3: dict[str, JsonValue] = {}
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "application/json"}, json=json_payload_3)
    client = build_client("https://oracle.test", with_structlogger(logger))

    client.get("/question")

    assert_that(logger.response).has_header("content-type", "application/json")


def test_logs_a_failed_response_status_code(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_4: dict[str, JsonValue] = {"message": "Not found"}
    httpx_mock.add_response(
        status_code=404,
        headers={"Content-Type": "application/json"},
        json=json_payload_4,
    )
    client = build_client("https://library.test", with_structlogger(logger))

    client.get("/books/absent")

    assert_that(logger.response).has_status_code(404)


def test_logs_a_failed_response_body(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_5: dict[str, JsonValue] = {"message": "Not found"}
    httpx_mock.add_response(
        status_code=404,
        headers={"Content-Type": "application/json"},
        json=json_payload_5,
    )
    client = build_client("https://library.test", with_structlogger(logger))

    client.get("/books/absent")

    assert_that(logger.response).has_body_field("message", "Not found")


def test_masks_the_authorization_header_by_default(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://vault.test", with_structlogger(logger))

    client.get("/keys", headers={"Authorization": "Bearer nWq7dLp2"})

    assert_that(logger.request).has_masked_header("authorization")


def test_keeps_the_authorization_value_out_of_the_log(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    credentials = "Bearer nWq7dLp2"
    httpx_mock.add_response(status_code=200)
    client = build_client("https://vault.test", with_structlogger(logger))

    client.get("/keys", headers={"Authorization": credentials})

    assert_that(logger.request).does_not_expose(credentials)


def test_masks_a_password_in_the_body_by_default(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://accounts.test", with_structlogger(logger))

    json_payload_6: dict[str, JsonValue] = {"login": "morgan", "password": "hunter2"}
    client.post("/login", json=json_payload_6)

    assert_that(logger.request).has_masked_body_field("password")


def test_keeps_ordinary_body_fields_readable(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://accounts.test", with_structlogger(logger))

    json_payload_7: dict[str, JsonValue] = {"login": "morgan", "password": "hunter2"}
    client.post("/login", json=json_payload_7)

    assert_that(logger.request).has_body_field("login", "morgan")


def test_masks_a_nested_password_by_default(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://accounts.test", with_structlogger(logger))

    json_payload_8: dict[str, JsonValue] = {"user": {"profile": {"password": "quiche-lorraine"}}}
    client.post("/signup", json=json_payload_8)

    assert_that(logger.request).does_not_expose("quiche-lorraine")


def test_masks_a_secret_inside_a_list_by_default(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://accounts.test", with_structlogger(logger))

    json_payload_9: dict[str, JsonValue] = {"sessions": [{"token": "zulu-9"}, {"token": "yankee-4"}]}
    client.post("/sessions", json=json_payload_9)

    assert_that(logger.request).does_not_expose("yankee-4")


def test_keeps_nested_ordinary_fields_readable(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://accounts.test", with_structlogger(logger))

    json_payload_10: dict[str, JsonValue] = {"user": {"profile": {"city": "Выборг", "password": "quiche"}}}
    client.post("/signup", json=json_payload_10)

    assert_that(logger.request).has_body_containing('"city": "Выборг"')


def test_keeps_nested_secrets_readable_when_default_masking_is_off(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://legacy.test", with_structlogger(logger, use_default_sanitize_keys=False))

    json_payload_11: dict[str, JsonValue] = {"user": {"password": "kilo-7"}}
    client.post("/signup", json=json_payload_11)

    assert_that(logger.request).has_body_containing('"password": "kilo-7"')


def test_masks_the_keys_it_was_asked_to_mask(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://crm.test", with_structlogger(logger, sanitize_keys=["contact.phone"]))

    json_payload_12: dict[str, JsonValue] = {"contact": {"phone": "+7 900 000-00-00", "city": "Пермь"}}
    client.post("/leads", json=json_payload_12)

    assert_that(logger.request).does_not_expose("+7 900 000-00-00")


def test_keeps_secrets_readable_when_default_masking_is_off(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://legacy.test", with_structlogger(logger, use_default_sanitize_keys=False))

    client.get("/ping", headers={"Authorization": "Bearer plain-token"})

    assert_that(logger.request).has_header("authorization", "Bearer plain-token")


def test_marks_headers_it_cannot_mask(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://broken.test", with_structlogger(logger, sanitize_keys=["*"]))

    client.get("/ping")

    assert_that(logger.request).has_field("headers", "<Error parse: ValueError>")


def test_marks_query_params_it_cannot_mask(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://broken.test", with_structlogger(logger, sanitize_keys=["*"]))

    client.get("/ping", params={"page": "2"})

    assert_that(logger.request).has_field("query_params", "<Error parse: ValueError>")


def test_delivers_the_response_even_when_masking_fails(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://broken.test", with_structlogger(logger, sanitize_keys=["*"]))

    response = client.get("/ping")

    assert_that(response.status_code).is_equal_to(200)


def test_logs_a_plain_text_request_body(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://notes.test", with_structlogger(logger))

    client.post("/notes", headers={"Content-Type": "text/plain"}, content=b"buy milk")

    assert_that(logger.request).has_body("buy milk")


def test_logs_a_plain_text_response_body(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "text/plain"}, content=b"pong")
    client = build_client("https://notes.test", with_structlogger(logger))

    client.get("/ping")

    assert_that(logger.response).has_body("pong")


def test_marks_a_request_body_of_unsupported_type(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://soap.test", with_structlogger(logger))

    client.post("/rpc", headers={"Content-Type": "application/xml"}, content=b"<call/>")

    assert_that(logger.request).has_body("<not logged, content-type: application/xml>")


def test_marks_a_response_body_of_unsupported_type(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "application/xml"}, content=b"<result/>")
    client = build_client("https://soap.test", with_structlogger(logger))

    client.get("/rpc")

    assert_that(logger.response).has_body("<not logged, content-type: application/xml>")


def test_marks_a_body_it_cannot_parse(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        content=b'{"first": "object"}{"second": "object"}',
    )
    client = build_client("https://flaky.test", with_structlogger(logger))

    client.get("/stream-of-objects")

    assert_that(logger.response).has_body("<Error parse: JSONDecodeError>")


def test_trims_an_overlong_binary_body(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    oversized = b"z" * (DEFAULT_OCTET_STREAM_LOG_MAXLENGTH * 3)
    client = build_client("https://uploads.test", with_structlogger(logger))

    client.post("/blobs", headers={"Content-Type": "application/octet-stream"}, content=oversized)

    assert_that(logger.request).has_body_of_length(DEFAULT_OCTET_STREAM_LOG_MAXLENGTH)


def test_marks_the_cut_in_a_trimmed_body(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    oversized = b"z" * (DEFAULT_OCTET_STREAM_LOG_MAXLENGTH * 3)
    client = build_client("https://uploads.test", with_structlogger(logger))

    client.post("/blobs", headers={"Content-Type": "application/octet-stream"}, content=oversized)

    assert_that(logger.request).has_body_containing("...")


def test_reports_a_binary_body_it_cannot_decode(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    undecodable = b"\xff\xfe\x00\x01"
    httpx_mock.add_response(status_code=200)
    client = build_client("https://uploads.test", with_structlogger(logger))

    client.post("/blobs", headers={"Content-Type": "application/octet-stream"}, content=undecodable)

    assert_that(logger.request).has_body(f"<binary content ({len(undecodable)} bytes)>")


def test_uses_the_configured_log_level(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    configure_logging(LoggingConfig(log_level=logging.DEBUG))
    client = build_client("https://verbose.test", with_structlogger(logger))

    client.get("/health")

    assert_that(logger.request).has_level(logging.DEBUG)


def test_prefers_the_log_level_given_to_the_option(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    configure_logging(LoggingConfig(log_level=logging.DEBUG))
    client = build_client("https://verbose.test", with_structlogger(logger, log_level=logging.WARNING))

    client.get("/health")

    assert_that(logger.request).has_level(logging.WARNING)


def test_indents_the_body_as_requested(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_client("https://pretty.test", with_structlogger(logger, json_indent=4))

    json_payload_13: dict[str, JsonValue] = {"shape": "circle"}
    client.post("/echo", json=json_payload_13)

    assert_that(logger.request).has_body('{\n    "shape": "circle"\n}')


def test_prefers_a_zero_indent_over_the_global_one(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    configure_logging(LoggingConfig(json_indent=8))
    client = build_client("https://pretty.test", with_structlogger(logger, json_indent=0))

    json_payload_14: dict[str, JsonValue] = {"shape": "square"}
    client.post("/echo", json=json_payload_14)

    assert_that(logger.request).has_body('{\n"shape": "square"\n}')


def test_falls_back_to_the_global_indent(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    configure_logging(LoggingConfig(json_indent=2))
    client = build_client("https://pretty.test", with_structlogger(logger))

    json_payload_15: dict[str, JsonValue] = {"shape": "hexagon"}
    client.post("/echo", json=json_payload_15)

    assert_that(logger.request).has_body('{\n  "shape": "hexagon"\n}')


def test_logs_a_streaming_request(logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "text/plain"}, content=b"chunk")
    client = build_client("https://cdn.test", with_structlogger(logger))

    with client.stream("GET", "/archive.zip") as response:
        response.read()

    assert_that(logger.request).has_url("https://cdn.test/archive.zip")


def test_leaves_a_streaming_response_body_unread(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_16: dict[str, JsonValue] = {"items": [1, 2, 3]}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_16,
    )
    client = build_client("https://cdn.test", with_structlogger(logger))

    with client.stream("GET", "/feed") as response:
        response.read()

    assert_that(logger.response).has_body("<streamed content>")


def test_logs_a_streaming_response_status_code(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_17: dict[str, JsonValue] = {"error": "boom"}
    httpx_mock.add_response(
        status_code=500,
        headers={"Content-Type": "application/json"},
        json=json_payload_17,
    )
    client = build_client("https://cdn.test", with_structlogger(logger))

    with client.stream("GET", "/feed") as response:
        response.read()

    assert_that(logger.response).has_status_code(500)


def test_masks_secrets_in_a_streaming_request(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "text/plain"}, content=b"ok")
    client = build_client("https://cdn.test", with_structlogger(logger))

    json_payload_27: dict[str, JsonValue] = {"api_key": "kX92mm", "file": "photo.png"}
    with client.stream("POST", "/upload", json=json_payload_27) as response:
        response.read()

    assert_that(logger.request).has_masked_body_field("api_key")


def test_logs_every_attempt_of_an_auth_retry(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_18: dict[str, JsonValue] = {"error": "expired"}
    httpx_mock.add_response(
        status_code=401,
        headers={"Content-Type": "application/json"},
        json=json_payload_18,
    )
    json_payload_19: dict[str, JsonValue] = {"balance": 120}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_19,
    )
    client = build_client("https://wallet.test", with_structlogger(logger), with_auth(RetryingAuth()))

    client.get("/balance")

    assert_that(logger.requests).is_length(2)


def test_logs_the_rejected_attempt_of_an_auth_retry(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_20: dict[str, JsonValue] = {"error": "expired"}
    httpx_mock.add_response(
        status_code=401,
        headers={"Content-Type": "application/json"},
        json=json_payload_20,
    )
    json_payload_21: dict[str, JsonValue] = {"balance": 120}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_21,
    )
    client = build_client("https://wallet.test", with_structlogger(logger), with_auth(RetryingAuth()))

    client.get("/balance")

    assert_that(logger.responses[0]).has_body_field("error", "expired")


def test_logs_the_accepted_attempt_of_an_auth_retry(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_22: dict[str, JsonValue] = {"error": "expired"}
    httpx_mock.add_response(
        status_code=401,
        headers={"Content-Type": "application/json"},
        json=json_payload_22,
    )
    json_payload_23: dict[str, JsonValue] = {"balance": 120}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_23,
    )
    client = build_client("https://wallet.test", with_structlogger(logger), with_auth(RetryingAuth()))

    client.get("/balance")

    assert_that(logger.responses[1]).has_body_field("balance", 120)


def test_keeps_the_response_content_readable(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    expected_content = b'{"city": "Kazan"}'
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "application/json"}, content=expected_content)
    client = build_client("https://geo.test", with_structlogger(logger))

    response = client.get("/city")

    assert_that(response.content).is_equal_to(expected_content)


def test_keeps_the_response_json_readable(
    logger: FakeStructLogger, build_client: BuildClient, httpx_mock: HTTPXMock
) -> None:
    expected_payload = {"city": "Kazan"}
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "application/json"}, json=expected_payload)
    client = build_client("https://geo.test", with_structlogger(logger))

    response = client.get("/city")

    assert_that(cast("object", response.json())).is_equal_to(expected_payload)


@pytest.mark.asyncio
async def test_logs_a_request_of_an_async_client(
    logger: FakeStructLogger, build_async_client: BuildAsyncClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_async_client("https://async.test", with_structlogger(logger))

    await client.get("/tick")

    assert_that(logger.request).has_url("https://async.test/tick")


@pytest.mark.asyncio
async def test_logs_a_response_body_of_an_async_client(
    logger: FakeStructLogger, build_async_client: BuildAsyncClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_24: dict[str, JsonValue] = {"tick": 8}
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "application/json"}, json=json_payload_24)
    client = build_async_client("https://async.test", with_structlogger(logger))

    await client.get("/tick")

    assert_that(logger.response).has_body_field("tick", 8)


@pytest.mark.asyncio
async def test_masks_secrets_of_an_async_client(
    logger: FakeStructLogger, build_async_client: BuildAsyncClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_25: dict[str, JsonValue] = {"token": "s3cr3t"}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_25,
    )
    client = build_async_client("https://async.test", with_structlogger(logger))

    await client.get("/session")

    assert_that(logger.response).does_not_expose("s3cr3t")


@pytest.mark.asyncio
async def test_links_the_async_response_to_its_request(
    logger: FakeStructLogger, build_async_client: BuildAsyncClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=200)
    client = build_async_client("https://async.test", with_structlogger(logger))

    await client.get("/tick")

    assert_that(logger.response).has_same_trace_id_as(logger.request)


@pytest.mark.asyncio
async def test_leaves_an_async_streaming_response_body_unread(
    logger: FakeStructLogger, build_async_client: BuildAsyncClient, httpx_mock: HTTPXMock
) -> None:
    json_payload_26: dict[str, JsonValue] = {"items": [4, 5]}
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=json_payload_26,
    )
    client = build_async_client("https://async.test", with_structlogger(logger))

    async with client.stream("GET", "/feed") as response:
        await response.aread()

    assert_that(logger.response).has_body("<streamed content>")


def test_keeps_sensitive_values_out_of_parser_error_diagnostics(
    logger: FakeStructLogger,
    build_client: BuildClient,
    httpx_mock: HTTPXMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    confidential_value = "inspection-only-sensitive-value"
    httpx_mock.add_response(status_code=200)
    client = build_client("https://private.test", with_structlogger(logger, sanitize_keys=["*"]))

    client.post("/profile", json={"password": confidential_value})

    assert_that(caplog.text).does_not_contain(confidential_value)
