from typing import TYPE_CHECKING

import httpx
from assertpy import assert_that
from http_client import HttpClient, options
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment

if TYPE_CHECKING:
    from .json_types import JsonValue

MASK = "****"


def test_masks_authorization_header_by_default(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient(
        "https://billing.test",
        options.with_auth(httpx.BasicAuth("cashier", "hunter2")),
        wrap_requests_in_steps(),
    ) as client:
        client.get("/invoices")

    assert_attachment(report.request_attachment).has_json_value("headers.authorization", MASK)


def test_keeps_authorization_header_when_defaults_disabled(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient(
        "https://billing.test",
        options.with_auth(httpx.BasicAuth("cashier", "hunter2")),
        wrap_requests_in_steps(use_default_sanitize_keys=False),
    ) as client:
        client.get("/invoices")

    assert_attachment(report.request_attachment).shows("Basic ")


def test_masks_query_parameter(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://maps.test", wrap_requests_in_steps()) as client:
        client.get("/geocode", params={"token": "k3y-from-vault", "city": "Пермь"})

    assert_attachment(report.request_attachment).has_json_value("query_params.token", MASK)


def test_keeps_ordinary_query_parameter(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://maps.test", wrap_requests_in_steps()) as client:
        client.get("/geocode", params={"token": "k3y-from-vault", "city": "Пермь"})

    assert_attachment(report.request_attachment).has_json_value("query_params.city", "Пермь")


def test_keeps_query_out_of_url_field(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://maps.test", wrap_requests_in_steps()) as client:
        client.get("/geocode", params={"token": "k3y-from-vault"})

    assert_attachment(report.request_attachment).has_json_value("url", "https://maps.test/geocode")


def test_masks_query_parameter_in_curl(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://maps.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        client.get("/geocode", params={"api_key": "s3cr3t-key", "city": "Омск"})

    assert_attachment(report.request_attachment).hides("s3cr3t-key")


def test_keeps_ordinary_query_parameter_in_curl(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://maps.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        client.get("/geocode", params={"api_key": "s3cr3t-key", "limit": 5})

    assert_attachment(report.request_attachment).shows("limit=5")


def test_masks_query_parameter_in_step_title(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://maps.test", wrap_requests_in_steps(show_query_params=True)) as client:
        client.get("/geocode", params={"secret": "do-not-show-me"})

    assert_that(report.steps[0].title).is_equal_to(f"[GET] /geocode?secret={MASK}")


def test_masks_custom_key_in_request_body(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://crm.test", wrap_requests_in_steps(sanitize_keys=["client.pin"])) as client:
        json_payload_3: dict[str, JsonValue] = {"client": {"name": "Мария", "pin": "4815"}}
        client.post("/leads", json=json_payload_3)

    assert_attachment(report.request_attachment).has_json_value("body.client.pin", MASK)


def test_masks_secret_in_response_body(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"access_token": "opaque-jwt", "expires_in": 900}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_1)

    with HttpClient("https://auth.test", wrap_requests_and_responses_in_steps()) as client:
        client.post("/oauth/token")

    assert_attachment(report.response_attachment).has_json_value("access_token", MASK)


def test_keeps_ordinary_field_in_response_body(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_2: dict[str, JsonValue] = {"access_token": "opaque-jwt", "expires_in": 900}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_2)

    with HttpClient("https://auth.test", wrap_requests_and_responses_in_steps()) as client:
        client.post("/oauth/token")

    assert_attachment(report.response_attachment).has_json_value("expires_in", 900)


def test_keeps_repeated_query_parameters(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://catalog.test", wrap_requests_in_steps()) as client:
        client.get("/items", params=[("tag", "new"), ("tag", "sale")])

    assert_attachment(report.request_attachment).has_json_value("query_params.tag", ["new", "sale"])


def test_keeps_repeated_query_parameters_in_step_title(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://catalog.test", wrap_requests_in_steps(show_query_params=True)) as client:
        client.get("/items", params=[("tag", "new"), ("tag", "sale")])

    assert_that(report.steps[0].title).is_equal_to("[GET] /items?tag=new&tag=sale")


def test_keeps_repeated_query_parameters_in_curl(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://catalog.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        client.get("/items", params=[("tag", "new"), ("tag", "sale")])

    assert_attachment(report.request_attachment).shows("tag=new&tag=sale")
