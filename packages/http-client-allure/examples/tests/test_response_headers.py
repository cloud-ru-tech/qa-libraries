import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

from .assertions import assert_that

pytestmark = allure.feature("Заголовки ответа")


@allure.title("Заголовки ответа попадают в отчет отдельным вложением")
def test_attaches_response_headers(httpbin_url: str) -> None:
    order_id = "A-1024"

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/response-headers", params={"x-order-id": order_id})

    assert_that(response).has_response_header("x-order-id", order_id)


@allure.title("Секрет в заголовке ответа в отчете замаскирован")
def test_masks_secret_in_response_header(httpbin_url: str) -> None:
    issued_cookie = "session=s3cr3t"

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/response-headers", params={"set-cookie": issued_cookie})

    assert_that(response).has_response_header("set-cookie", issued_cookie)


@allure.title("attach_response_headers=False убирает заголовки ответа из отчета")
def test_hides_response_headers(httpbin_url: str) -> None:
    region = "ru-central-1"
    option = wrap_requests_and_responses_in_steps(attach_response_headers=False)

    with HttpClient(httpbin_url, option) as client:
        response = client.get("/response-headers", params={"x-region": region})

    assert_that(response).has_response_header("x-region", region)


@allure.title("attach_response=False оставляет в отчете только заголовки ответа")
def test_attaches_headers_without_response_body(httpbin_url: str) -> None:
    served_by = "orders-7c4f"
    option = wrap_requests_and_responses_in_steps(attach_response=False)

    with HttpClient(httpbin_url, option) as client:
        response = client.get("/response-headers", params={"x-served-by": served_by})

    assert_that(response).has_response_header("x-served-by", served_by)


@allure.title("У ответа без тела заголовки в отчете все равно есть")
def test_attaches_headers_for_response_without_body(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.delete("/status/204")

    assert_that(response).has_empty_body()
