import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

from .assertions import assert_that

pytestmark = allure.feature("Оформление вложений")


@allure.title("Длинное вложение обрезается по max_attach_length")
def test_truncates_long_attachment(httpbin_url: str) -> None:
    catalog = {"items": [{"id": number, "name": f"Чай сорт {number}"} for number in range(200)]}

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps(max_attach_length=500)) as client:
        response = client.post("/anything/catalog", json=catalog)

    assert_that(response).echoes_json(catalog)


@allure.title("Без max_attach_length то же вложение попадает в отчет целиком")
def test_attaches_long_payload_in_full(httpbin_url: str) -> None:
    routes = {"routes": [{"stop": number, "city": f"Город {number}"} for number in range(150)]}

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.post("/anything/routes", json=routes)

    assert_that(response).echoes_json(routes)


@allure.title("json_dumps_kwargs форматирует JSON во вложении")
def test_formats_json_with_indent(httpbin_url: str) -> None:
    subscription = {"plan": "pro", "seats": 25}
    option = wrap_requests_and_responses_in_steps(json_dumps_kwargs={"indent": 4, "sort_keys": True})

    with HttpClient(httpbin_url, option) as client:
        response = client.post("/anything/subscriptions", json=subscription)

    assert_that(response).echoes_json(subscription)


@allure.title("Кириллица во вложении по умолчанию читается")
def test_keeps_cyrillic_readable(httpbin_url: str) -> None:
    delivery = {"city": "Пермь", "comment": "Позвонить перед доставкой"}

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.post("/anything/deliveries", json=delivery)

    assert_that(response).echoes_json(delivery)


@allure.title("json_dumps_kwargs заменяет настройки по умолчанию целиком")
def test_replaces_default_json_dumps_kwargs(httpbin_url: str) -> None:
    address = {"city": "Ярославль"}
    option = wrap_requests_and_responses_in_steps(json_dumps_kwargs={"indent": 4})

    with HttpClient(httpbin_url, option) as client:
        response = client.post("/anything/addresses", json=address)

    assert_that(response).echoes_json(address)
