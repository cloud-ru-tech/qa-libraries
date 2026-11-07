from collections.abc import Iterator

import httpx
import pytest
from assertpy import assert_that
from http_client import AsyncHttpClient, HttpClient
from http_client_allure import wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment, assert_report

JSON_HEADERS = {"content-type": "application/json"}
BROKEN_JSON = b"{not-a-json"
BODY_FAILURE = "генератор тела упал"


def failing_body() -> Iterator[bytes]:
    yield b"first"
    raise ValueError(BODY_FAILURE)


def build_broken_json_request(client: AsyncHttpClient | HttpClient) -> httpx.Request:
    return client.client.build_request("POST", "/orders", content=BROKEN_JSON, headers=JSON_HEADERS)


def send_failing_body(client: HttpClient) -> None:
    request = client.client.build_request("POST", "/parts", content=failing_body())
    client.send(request)


@pytest.mark.usefixtures("report")
def test_returns_response_when_curl_serialization_fails(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.CREATED)

    with HttpClient("https://legacy.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        response = client.send(build_broken_json_request(client))

    assert_that(response.status_code, "ошибка оформления отчета не должна ломать успешный запрос").is_equal_to(
        codes.CREATED
    )


def test_attaches_error_note_when_curl_serialization_fails(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.CREATED)

    with HttpClient("https://legacy.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        client.send(build_broken_json_request(client))

    assert_attachment(report.attachments[0]).shows("Ошибка формирования вложения")


@pytest.mark.usefixtures("report")
async def test_returns_response_when_async_curl_serialization_fails(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.CREATED)

    async with AsyncHttpClient("https://legacy.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        response = await client.send(build_broken_json_request(client))

    assert_that(response.status_code, "ошибка оформления отчета не должна ломать успешный запрос").is_equal_to(
        codes.CREATED
    )


def test_creates_step_when_request_body_generator_fails(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, is_optional=True)

    with (
        HttpClient("https://uploads.test", wrap_requests_in_steps()) as client,
        pytest.raises(ValueError, match=BODY_FAILURE),
    ):
        send_failing_body(client)

    assert_report(report).has_single_step("[POST] /parts")


def test_marks_step_failed_when_request_body_generator_fails(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, is_optional=True)

    with (
        HttpClient("https://uploads.test", wrap_requests_in_steps()) as client,
        pytest.raises(ValueError, match=BODY_FAILURE),
    ):
        send_failing_body(client)

    assert_report(report).has_failed_step("[POST] /parts")


@pytest.mark.usefixtures("report")
def test_sends_request_when_sanitize_key_is_malformed(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://legacy.test", wrap_requests_in_steps(sanitize_keys=["items["])) as client:
        response = client.get("/orders", params={"page": 1})

    assert_that(response.status_code, "опечатка в sanitize_keys не должна срывать отправку").is_equal_to(codes.OK)
