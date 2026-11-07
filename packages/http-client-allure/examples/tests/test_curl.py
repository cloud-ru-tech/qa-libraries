import allure
import httpx
from http_client import HttpClient, options
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps

from .assertions import assert_that

pytestmark = allure.feature("serialize_request_to_curl")


@allure.title("Запрос прикладывается готовой командой curl")
def test_attaches_request_as_curl(httpbin_url: str) -> None:
    status = "shipped"

    with HttpClient(httpbin_url, wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        response = client.get("/anything/parcels", params={"status": status, "page": 4})

    assert_that(response).echoes_query_param("status", [status])


@allure.title("Тело POST запроса попадает в команду curl")
def test_attaches_post_body_as_curl(httpbin_url: str) -> None:
    parcel = {"track": "RA123456789RU", "weight_kg": 1.2}

    with HttpClient(httpbin_url, wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        response = client.post("/anything/parcels", json=parcel)

    assert_that(response).echoes_json(parcel)


@allure.title("Секреты в команде curl замаскированы")
def test_masks_secrets_in_curl(httpbin_url: str) -> None:
    client_options = (
        options.with_auth(httpx.BasicAuth("courier", "hunter2")),
        wrap_requests_in_steps(serialize_request_to_curl=True),
    )

    with HttpClient(httpbin_url, *client_options) as client:
        response = client.get("/basic-auth/courier/hunter2")

    assert_that(response).has_json_field("authorized", expected=True)


@allure.title("curl включается вместе с данными ответа")
def test_attaches_curl_and_response(httpbin_url: str) -> None:
    option = wrap_requests_and_responses_in_steps(serialize_request_to_curl=True)

    with HttpClient(httpbin_url, option) as client:
        response = client.get("/json")

    assert_that(response).has_json_field("slideshow.date", expected="date of publication")
