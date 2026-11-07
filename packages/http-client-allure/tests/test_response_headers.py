from typing import TYPE_CHECKING

import allure
import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment, assert_report

if TYPE_CHECKING:
    from .json_types import JsonValue

MASK = "****"


def test_attaches_response_headers(report: Report, httpx_mock: HTTPXMock) -> None:
    trace_id = "0f75c97f-1926-4bf3-8c0d-98a1e5beb40f"
    httpx_mock.add_response(status_code=codes.OK, headers={"x-trace-id": trace_id})

    with HttpClient("https://orders.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/orders/42")

    assert_attachment(report.response_headers_attachment).has_json_value("x-trace-id", trace_id)


def test_names_headers_attachment_with_status(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.CREATED)

    with HttpClient("https://orders.test", wrap_requests_and_responses_in_steps()) as client:
        client.post("/orders")

    assert_attachment(report.response_headers_attachment).has_name("Response headers: status = 201 [Created]")


def test_attaches_headers_as_json(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, headers={"x-page": "3"})

    with HttpClient("https://catalog.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/goods")

    assert_attachment(report.response_headers_attachment).has_type(allure.attachment_type.JSON)


def test_masks_secret_in_response_header(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, headers={"set-cookie": "session=s3cr3t; Path=/"})

    with HttpClient("https://accounts.test", wrap_requests_and_responses_in_steps()) as client:
        client.post("/login")

    assert_attachment(report.response_headers_attachment).has_json_value("set-cookie", MASK)


def test_keeps_secret_in_response_header_when_defaults_disabled(report: Report, httpx_mock: HTTPXMock) -> None:
    issued_cookie = "session=s3cr3t; Path=/"
    httpx_mock.add_response(status_code=codes.OK, headers={"set-cookie": issued_cookie})

    with HttpClient(
        "https://accounts.test",
        wrap_requests_and_responses_in_steps(use_default_sanitize_keys=False),
    ) as client:
        client.post("/login")

    assert_attachment(report.response_headers_attachment).has_json_value("set-cookie", issued_cookie)


def test_skips_headers_when_disabled(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"total": 7}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_1)

    with HttpClient(
        "https://catalog.test",
        wrap_requests_and_responses_in_steps(attach_response_headers=False),
    ) as client:
        client.get("/goods")

    assert_report(report).has_attachment_names(["Request details", "Response content"])


def test_attaches_headers_without_response_body(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_2: dict[str, JsonValue] = {"total": 7}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_2)

    with HttpClient(
        "https://catalog.test",
        wrap_requests_and_responses_in_steps(attach_response=False),
    ) as client:
        client.get("/goods")

    assert_report(report).has_attachment_names(["Request details", "Response headers: status = 200 [OK]"])


def test_attaches_headers_for_response_without_body(report: Report, httpx_mock: HTTPXMock) -> None:
    location = "/cache/7"
    httpx_mock.add_response(status_code=codes.NO_CONTENT, headers={"location": location})

    with HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client:
        client.delete("/cache/7")

    assert_attachment(report.response_headers_attachment).has_json_value("location", location)


def test_attaches_headers_for_unread_stream(report: Report, httpx_mock: HTTPXMock) -> None:
    chunk_encoding = "chunked"
    httpx_mock.add_response(
        status_code=codes.OK,
        content=b"z" * 2048,
        headers={"transfer-encoding": chunk_encoding},
    )

    with (
        HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/dump.bin") as response,
    ):
        [*response.iter_bytes()]

    assert_attachment(report.response_headers_attachment).has_json_value("transfer-encoding", chunk_encoding)


def test_skips_headers_on_connection_error(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with (
        HttpClient("https://offline.test", wrap_requests_and_responses_in_steps()) as client,
        pytest.raises(httpx.ConnectError),
    ):
        client.get("/ping")

    assert_report(report).has_attachment_names(["Request details"])


async def test_attaches_async_response_headers(report: Report, httpx_mock: HTTPXMock) -> None:
    served_by = "orders-7c4f"
    httpx_mock.add_response(status_code=codes.OK, headers={"x-served-by": served_by})

    async with AsyncHttpClient("https://orders.test", wrap_requests_and_responses_in_steps()) as client:
        await client.get("/orders/17")

    assert_attachment(report.response_headers_attachment).has_json_value("x-served-by", served_by)


def test_truncates_long_headers_attachment(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, headers={"x-debug-trace": "step," * 300})

    with HttpClient("https://orders.test", wrap_requests_and_responses_in_steps(max_attach_length=64)) as client:
        client.get("/orders/42")

    assert_attachment(report.response_headers_attachment).is_truncated()


def test_skips_headers_without_response_option(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, headers={"x-trace-id": "3f1c"})

    with HttpClient("https://orders.test", wrap_requests_in_steps()) as client:
        client.get("/orders/42")

    assert_report(report).has_attachment_names(["Request details"])
