import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_in_steps

from .assertions import assert_that

pytestmark = allure.feature("Заголовок шага")


@allure.title("По умолчанию в заголовке только метод и путь")
def test_shows_method_and_path_by_default(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_in_steps()) as client:
        response = client.get("/anything/warehouses")

    assert_that(response).hits_path("/anything/warehouses")


@allure.title("show_host=True добавляет в заголовок хост")
def test_shows_host(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_in_steps(show_host=True)) as client:
        response = client.get("/anything/couriers")

    assert_that(response).carries_header("host")


@allure.title("show_query_params=True добавляет в заголовок query параметры")
def test_shows_query_params(httpbin_url: str) -> None:
    warehouse = "novosibirsk"

    with HttpClient(httpbin_url, wrap_requests_in_steps(show_query_params=True)) as client:
        response = client.get("/anything/stock", params={"warehouse": warehouse, "page": 2})

    assert_that(response).echoes_query_param("warehouse", [warehouse])


@allure.title("Повторяющиеся query параметры не схлопываются в заголовке")
def test_shows_repeated_query_params(httpbin_url: str) -> None:
    tags = ["new", "sale"]

    with HttpClient(httpbin_url, wrap_requests_in_steps(show_query_params=True)) as client:
        response = client.get("/anything/items", params=[("tag", tag) for tag in tags])

    assert_that(response).echoes_query_param("tag", tags)


@allure.title("Секрет в query параметре маскируется и в заголовке шага")
def test_masks_secret_query_param(httpbin_url: str) -> None:
    credential = "s3cret-from-vault"
    option = wrap_requests_in_steps(show_host=True, show_query_params=True)

    with HttpClient(httpbin_url, option) as client:
        response = client.get("/anything/stock", params={"token": credential, "page": 2})

    assert_that(response).echoes_query_param("token", [credential])
