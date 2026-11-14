import allure
import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient, options
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes

from .assertions import assert_that

pytestmark = allure.feature("Ошибки в отчете")


def check_status_inside_stream(client: HttpClient) -> None:
    """Read the stream and fail on the response status within the step."""
    with client.stream("GET", "/status/503") as response:
        response.read()
        response.raise_for_status()


@allure.title("Таймаут помечает шаг упавшим, но запрос остается в отчете")
def test_marks_step_failed_on_timeout(httpbin_url: str) -> None:
    client_options = (options.with_timeout(0.5), wrap_requests_and_responses_in_steps())

    with (
        HttpClient(httpbin_url, *client_options) as client,
        pytest.raises(httpx.ReadTimeout),
    ):
        client.get("/delay/3")


@allure.title("Оборванное соединение тоже попадает в отчет")
def test_marks_step_failed_on_connection_error() -> None:
    with (
        HttpClient("http://127.0.0.1:1", wrap_requests_in_steps()) as client,
        pytest.raises(httpx.ConnectError),
    ):
        client.get("/orders")


@allure.title("Асинхронный таймаут тоже помечает шаг упавшим")
async def test_marks_async_step_failed_on_timeout(httpbin_url: str) -> None:
    client_options = (options.with_timeout(0.3), wrap_requests_and_responses_in_steps())

    async with AsyncHttpClient(httpbin_url, *client_options) as client:
        with pytest.raises(httpx.ReadTimeout):
            await client.get("/delay/2")


@allure.title("Ошибка внутри потока не мешает данным ответа попасть в отчет")
def test_attaches_response_when_stream_breaks(httpbin_url: str) -> None:
    with (
        HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        check_status_inside_stream(client)


@allure.title("Ответ с ошибкой сервера не делает шаг красным")
def test_keeps_step_green_on_error_status(httpbin_url: str) -> None:
    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = client.get("/status/500")

    assert_that(response).has_status(codes.INTERNAL_SERVER_ERROR)
