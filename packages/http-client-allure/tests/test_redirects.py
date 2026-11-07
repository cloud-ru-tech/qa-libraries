from typing import TYPE_CHECKING

from assertpy import assert_that
from http_client import HttpClient, options
from http_client_allure import wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment

if TYPE_CHECKING:
    from .json_types import JsonValue

FINAL_URL = "https://shop.test/checkout"


def follow_redirect(client: HttpClient) -> None:
    json_payload_1: dict[str, JsonValue] = {"sku": "TEA-42"}
    client.post("/cart", json=json_payload_1)


def build_client() -> HttpClient:
    return HttpClient(
        "https://shop.test",
        options.with_follow_redirects(),
        wrap_requests_in_steps(),
    )


def test_attaches_method_of_original_request(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.FOUND, headers={"location": FINAL_URL})
    httpx_mock.add_response(status_code=codes.OK, url=FINAL_URL)

    with build_client() as client:
        follow_redirect(client)

    assert_attachment(report.request_attachment).has_json_value("method", "POST")


def test_attaches_url_of_original_request(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.FOUND, headers={"location": FINAL_URL})
    httpx_mock.add_response(status_code=codes.OK, url=FINAL_URL)

    with build_client() as client:
        follow_redirect(client)

    assert_attachment(report.request_attachment).has_json_value("url", "https://shop.test/cart")


def test_attaches_body_of_original_request(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.FOUND, headers={"location": FINAL_URL})
    httpx_mock.add_response(status_code=codes.OK, url=FINAL_URL)

    with build_client() as client:
        follow_redirect(client)

    assert_attachment(report.request_attachment).has_json_value("body.sku", "TEA-42")


def test_names_step_after_original_request(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.FOUND, headers={"location": FINAL_URL})
    httpx_mock.add_response(status_code=codes.OK, url=FINAL_URL)

    with build_client() as client:
        follow_redirect(client)

    assert_that(report.steps[0].title).is_equal_to("[POST] /cart")
