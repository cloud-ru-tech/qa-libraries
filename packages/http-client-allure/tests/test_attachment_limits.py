from typing import TYPE_CHECKING

import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment

if TYPE_CHECKING:
    from .json_types import JsonValue


def test_truncates_long_request_attachment(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://import.test", wrap_requests_in_steps(max_attach_length=48)) as client:
        json_payload_3: dict[str, JsonValue] = {"rows": ["row"] * 200}
        client.post("/batches", json=json_payload_3)

    assert_attachment(report.request_attachment).is_truncated()


def test_reports_full_length_of_truncated_attachment(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://import.test", wrap_requests_in_steps(max_attach_length=48)) as client:
        json_payload_4: dict[str, JsonValue] = {"rows": ["row"] * 200}
        client.post("/batches", json=json_payload_4)

    assert_attachment(report.request_attachment).shows("символов")


def test_downgrades_truncated_json_attachment_to_text(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://import.test", wrap_requests_in_steps(max_attach_length=48)) as client:
        json_payload_5: dict[str, JsonValue] = {"rows": ["row"] * 200}
        client.post("/batches", json=json_payload_5)

    assert_attachment(report.request_attachment).has_type(allure.attachment_type.TEXT)


def test_keeps_json_type_when_attachment_fits_the_limit(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://import.test", wrap_requests_in_steps(max_attach_length=100_000)) as client:
        json_payload_6: dict[str, JsonValue] = {"rows": ["row"]}
        client.post("/batches", json=json_payload_6)

    assert_attachment(report.request_attachment).has_type(allure.attachment_type.JSON)


def test_keeps_attachment_intact_when_it_fits_the_limit(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://import.test", wrap_requests_in_steps(max_attach_length=100_000)) as client:
        json_payload_7: dict[str, JsonValue] = {"rows": ["row"]}
        client.post("/batches", json=json_payload_7)

    assert_attachment(report.request_attachment).has_json_value("body.rows", ["row"])


def test_keeps_attachment_intact_without_limit(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"accepted": 900}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_1)

    with HttpClient("https://import.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/batches/9")

    assert_attachment(report.response_attachment).is_not_truncated()


def test_truncates_long_response_attachment(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_2: dict[str, JsonValue] = {"notes": ["note"] * 300}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_2)

    with HttpClient("https://import.test", wrap_requests_and_responses_in_steps(max_attach_length=64)) as client:
        client.get("/batches/9")

    assert_attachment(report.response_attachment).is_truncated()
