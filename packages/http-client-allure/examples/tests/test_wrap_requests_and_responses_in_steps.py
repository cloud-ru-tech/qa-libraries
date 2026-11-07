import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps
from httpx import codes

from .assertions import assert_that

pytestmark = allure.feature("wrap_requests_and_responses_in_steps")


@allure.title("Запрос и ответ лежат рядом в одном шаге")
def test_attaches_request_and_response(httpbin_url: str) -> None:
    ticket = {"seat": "12C", "flight": "SU1743"}

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.post("/anything/tickets", json=ticket)

    assert_that(response).echoes_json(ticket)


@allure.title("JSON ответ попадает в отчет разобранным")
def test_attaches_json_response(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/json")

    assert_that(response).has_json_field("slideshow.title", expected="Sample Slide Show")


@allure.title("Текстовый ответ попадает в отчет как есть")
def test_attaches_text_response(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/robots.txt")

    assert_that(response).has_text("User-agent: *\nDisallow: /deny\n")


@allure.title("Пустой ответ не создает вложения")
def test_skips_attachment_for_empty_response(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/status/204")

    assert_that(response).has_empty_body()


@allure.title("Ответ с ошибкой виден в отчете, шаг остается зеленым")
def test_attaches_error_response(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/status/418")

    assert_that(response).has_text("I'm a teapot!")


@allure.title("attach_response=False убирает из отчета только данные ответа")
def test_attaches_request_only(httpbin_url: str) -> None:
    payment = {"amount": 1499, "currency": "RUB"}

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps(attach_response=False)) as client:
        response = client.post("/anything/payments", json=payment)

    assert_that(response).echoes_json(payment)


@allure.title("attach_request=False оставляет в отчете только данные ответа")
def test_attaches_response_only(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps(attach_request=False)) as client:
        response = client.get("/status/451")

    assert_that(response).has_status(codes.UNAVAILABLE_FOR_LEGAL_REASONS)
