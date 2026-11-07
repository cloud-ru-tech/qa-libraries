from assertpy import assert_that
from http_client import HttpClient
from http_client_allure import wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock
from syrupy.assertion import SnapshotAssertion

from .allure_recorder import Report
from .assertions import assert_report
from .case_types import parameterize_cases
from .test_wrap_requests_in_steps_cases import Scenario


@parameterize_cases("case")
def test_attaches_request_details(
    case: Scenario,
    report: Report,
    httpx_mock: HTTPXMock,
    snapshot: SnapshotAssertion,
) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with case.client as client:
        client.send(case.request)

    assert_that(case.prepare_snapshot(report.request_attachment.body)).is_equal_to(snapshot)


@parameterize_cases("case")
def test_names_step_after_request(case: Scenario, report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with case.client as client:
        client.send(case.request)

    assert_report(report).has_single_step(case.step_message)


def test_wraps_request_in_step_without_attachment(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://tickets.test", wrap_requests_in_steps(attach_request=False)) as client:
        client.get("/events")

    assert_report(report).has_single_step("[GET] /events")


def test_attaches_nothing_when_attachment_disabled(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://tickets.test", wrap_requests_in_steps(attach_request=False)) as client:
        client.get("/events")

    assert_report(report).has_attachments_count(0)
