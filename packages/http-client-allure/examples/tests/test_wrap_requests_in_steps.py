from typing import TYPE_CHECKING

import allure
from http_client import HttpClient, options
from http_client_allure import wrap_requests_in_steps
from httpx import codes

from .assertions import assert_that

if TYPE_CHECKING:
    from .json_types import JsonValue

pytestmark = allure.feature("wrap_requests_in_steps")


@allure.title("Запрос становится отдельным шагом отчета")
def test_wraps_request_in_step(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_in_steps()) as client:
        response = client.get("/get")

    assert_that(response).has_status(codes.OK)


@allure.title("Тело запроса видно в отчете")
def test_attaches_request_body(httpbin_url: str) -> None:
    book = {"title": "Мастер и Маргарита", "copies": 7}

    with HttpClient(httpbin_url, wrap_requests_in_steps()) as client:
        response = client.post("/anything/books", json=book)

    assert_that(response).echoes_json(book)


@allure.title("Данные ответа в отчет не попадают")
def test_does_not_attach_response(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_in_steps()) as client:
        response = client.get("/json")

    assert_that(response).has_json_field("slideshow.author", expected="Yours Truly")


@allure.title("attach_request=False оставляет в отчете шаги без вложений")
def test_creates_bare_steps(httpbin_url: str) -> None:
    probe = "bare-step"

    with HttpClient(httpbin_url, wrap_requests_in_steps(attach_request=False)) as client:
        response = client.get("/anything/ping", params={"probe": probe})

    assert_that(response).echoes_query_param("probe", [probe])


@allure.title("Каждый запрос клиента получает свой шаг")
def test_creates_step_per_request(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_in_steps()) as client:
        json_payload_1: dict[str, JsonValue] = {"number": "INV-9"}
        responses = [
            client.get("/uuid"),
            client.post("/anything/invoices", json=json_payload_1),
            client.delete("/anything/invoices/9"),
        ]

    assert_that(responses).extracting("status_code").is_equal_to([codes.OK, codes.OK, codes.OK])


@allure.title("Цепочка редиректов остается одним шагом с исходным запросом")
def test_wraps_redirect_chain_in_single_step(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, options.with_follow_redirects(), wrap_requests_in_steps()) as client:
        response = client.get("/redirect/3")

    assert_that(response).hits_path("/get")
