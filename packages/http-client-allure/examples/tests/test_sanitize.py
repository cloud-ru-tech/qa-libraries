import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps

from .assertions import assert_that

pytestmark = allure.feature("Маскирование секретов")


@allure.title("Общеизвестные секреты маскируются без настройки")
def test_masks_known_secrets_by_default(httpbin_url: str) -> None:
    credentials = {"login": "cashier", "password": "hunter2"}

    with HttpClient(httpbin_url, wrap_requests_in_steps()) as client:
        response = client.post("/anything/login", json=credentials, headers={"x-api-key": "k3y-from-vault"})

    assert_that(response).echoes_json(credentials)


@allure.title("Секрет в ответе тоже маскируется")
def test_masks_secret_in_response(httpbin_url: str) -> None:
    issued_jwt = "eyJhbGciOiJIUzI1NiJ9.demo"

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/bearer", headers={"authorization": f"Bearer {issued_jwt}"})

    assert_that(response).has_json_field("token", expected=issued_jwt)


@allure.title("sanitize_keys прячет ключи, о которых знает только проект")
def test_masks_custom_key(httpbin_url: str) -> None:
    lead = {"client": {"name": "Мария", "pin": "4815"}}

    with HttpClient(httpbin_url, wrap_requests_in_steps(sanitize_keys=["client.pin"])) as client:
        response = client.post("/anything/leads", json=lead)

    assert_that(response).echoes_json(lead)


@allure.title("Маска доходит до нужного ключа внутри списка")
def test_masks_key_inside_list(httpbin_url: str) -> None:
    fleet = {"devices": [{"id": 1, "key": "aaa"}, {"id": 2, "key": "bbb"}]}

    with HttpClient(httpbin_url, wrap_requests_in_steps(sanitize_keys=["devices.*.key"])) as client:
        response = client.post("/anything/devices", json=fleet)

    assert_that(response).echoes_json(fleet)


@allure.title("Свои ключи дополняют список по умолчанию, а не заменяют его")
def test_extends_default_keys(httpbin_url: str) -> None:
    account = {"password": "hunter2", "owner": {"pin": "1234"}}

    with HttpClient(httpbin_url, wrap_requests_in_steps(sanitize_keys=["owner.pin"])) as client:
        response = client.post("/anything/accounts", json=account)

    assert_that(response).echoes_json(account)


@allure.title("use_default_sanitize_keys=False показывает все, кроме перечисленного")
def test_shows_everything_except_listed_keys(httpbin_url: str) -> None:
    profile = {"password": "correct-horse", "owner": {"pin": "9911"}}
    option = wrap_requests_in_steps(sanitize_keys=["owner.pin"], use_default_sanitize_keys=False)

    with HttpClient(httpbin_url, option) as client:
        response = client.post("/anything/profiles", json=profile)

    assert_that(response).echoes_json(profile)
