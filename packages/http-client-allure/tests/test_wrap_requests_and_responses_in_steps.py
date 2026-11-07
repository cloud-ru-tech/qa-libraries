from typing import TYPE_CHECKING

from assertpy import assert_that
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock
from syrupy.assertion import SnapshotAssertion

from .allure_recorder import Report
from .assertions import assert_report
from .case_types import parameterize_cases
from .test_wrap_requests_and_responses_in_steps_cases import Scenario

if TYPE_CHECKING:
    from .json_types import JsonValue


@parameterize_cases("case")
def test_attaches_response_body(
    case: Scenario,
    report: Report,
    httpx_mock: HTTPXMock,
    snapshot: SnapshotAssertion,
) -> None:
    httpx_mock.add_response(**case.response_params)

    with case.client as client:
        client.get("/sample")

    assert_that(report.response_attachment.body).is_equal_to(snapshot)


@parameterize_cases("case")
def test_attaches_request_headers_and_content(case: Scenario, report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(**case.response_params)

    with case.client as client:
        client.get("/sample")

    assert_report(report).has_attachments_count(3)


def test_wraps_request_in_single_step(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"ok": True}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_1)

    with HttpClient("https://weather.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/forecast")

    assert_report(report).has_single_step("[GET] /forecast")


def test_skips_content_attachment_when_response_has_no_body(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.NO_CONTENT)

    with HttpClient("https://weather.test", wrap_requests_and_responses_in_steps()) as client:
        client.get("/forecast")

    assert_report(report).has_attachment_names(["Request details", "Response headers: status = 204 [No Content]"])
