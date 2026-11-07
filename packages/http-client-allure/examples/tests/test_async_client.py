import asyncio

import allure
from http_client import AsyncHttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

from .assertions import assert_that

pytestmark = allure.feature("Асинхронный клиент")


@allure.title("Асинхронный запрос попадает в отчет так же, как синхронный")
async def test_wraps_async_request_in_step(httpbin_url: str) -> None:
    async with AsyncHttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = await client.get("/json")

    assert_that(response).has_json_field("slideshow.author", expected="Yours Truly")


@allure.title("Тело асинхронного запроса и ответа видно в шаге")
async def test_attaches_async_bodies(httpbin_url: str) -> None:
    booking = {"room": 512, "nights": 2}

    async with AsyncHttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        response = await client.post("/anything/bookings", json=booking)

    assert_that(response).echoes_json(booking)


@allure.title("Параллельные запросы получают каждый свой шаг со своими данными")
async def test_wraps_concurrent_requests_in_separate_steps(httpbin_url: str) -> None:
    async with AsyncHttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        responses = await asyncio.gather(*(client.get("/uuid") for _ in range(5)))

    assert_that(responses).have_distinct_json_field("uuid")


@allure.title("Потоковый асинхронный запрос тоже попадает в отчет")
async def test_wraps_async_stream(httpbin_url: str) -> None:
    expected_lines = 3

    async with (
        AsyncHttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", f"/stream/{expected_lines}") as response,
    ):
        lines = [line async for line in response.aiter_lines() if line]

    assert_that(lines).is_length(expected_lines)
