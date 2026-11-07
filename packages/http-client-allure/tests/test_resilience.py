import allure
import httpx
import pytest
from assertpy import assert_that
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment, assert_report

MALFORMED_JSON = b"<html>502 Bad Gateway</html>"


@pytest.mark.usefixtures("report")
def test_sends_request_with_malformed_json_body(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.ACCEPTED)

    with HttpClient("https://legacy.test", wrap_requests_in_steps()) as client:
        request = client.client.build_request(
            "POST",
            "/soap",
            content=b"{broken",
            headers={"content-type": "application/json"},
        )
        response = client.send(request)

    assert_that(response.status_code, "оформление отчета не должно ломать запрос").is_equal_to(codes.ACCEPTED)


def test_attaches_malformed_json_request_body_as_text(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.ACCEPTED)

    with HttpClient("https://legacy.test", wrap_requests_in_steps()) as client:
        request = client.client.build_request(
            "POST",
            "/soap",
            content=b"{broken",
            headers={"content-type": "application/json"},
        )
        client.send(request)

    assert_attachment(report.request_attachment).has_json_value("body", "{broken")


def test_attaches_malformed_json_response_as_text(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        status_code=codes.BAD_GATEWAY,
        content=MALFORMED_JSON,
        headers={"content-type": "application/json"},
    )

    with HttpClient("https://legacy.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/status")

    assert_attachment(report.response_attachment).has_body(MALFORMED_JSON.decode())


def test_creates_step_on_connection_error(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with (
        HttpClient("https://offline.test", wrap_requests_and_responses_in_steps()) as client,
        pytest.raises(httpx.ConnectError),
    ):
        client.get("/ping")

    assert_report(report).has_single_step("[GET] /ping")


def test_attaches_binary_response_as_placeholder(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"\x89PNG\r\n\x1a\n\xff")

    with HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/favicon.png")

    assert_attachment(report.response_attachment).has_body("<binary data 9 bytes>")


def test_skips_response_attachment_when_body_is_empty(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.NO_CONTENT)

    with HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client:
        client.delete("/cache/7")

    assert_report(report).has_attachments_count(2)


def test_attaches_request_inside_step(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/health")

    assert_report(report).has_every_attachment_inside_step()


def test_attaches_json_string_response_as_json(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b'"accepted"', headers={"content-type": "application/json"})

    with HttpClient("https://queue.test", wrap_requests_and_responses_in_steps()) as client:
        client.post("/jobs")

    assert_attachment(report.response_attachment).has_type(allure.attachment_type.JSON)


def test_attaches_json_number_response_as_json(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"42", headers={"content-type": "application/json"})

    with HttpClient("https://queue.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/jobs/count")

    assert_attachment(report.response_attachment).has_json_body(42)


def test_attaches_malformed_json_response_as_text_type(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        status_code=codes.BAD_GATEWAY,
        content=MALFORMED_JSON,
        headers={"content-type": "application/json"},
    )

    with HttpClient("https://queue.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/jobs")

    assert_attachment(report.response_attachment).has_type(allure.attachment_type.TEXT)
