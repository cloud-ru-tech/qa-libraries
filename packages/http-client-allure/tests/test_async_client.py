from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that
from http_client import AsyncHttpClient
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment, assert_report

if TYPE_CHECKING:
    from .json_types import JsonValue


async def test_wraps_async_request_in_step(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.CREATED)

    async with AsyncHttpClient("https://shop.test", wrap_requests_in_steps()) as client:
        await client.post("/orders")

    assert_report(report).has_single_step("[POST] /orders")


async def test_attaches_async_request_body(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.CREATED)

    async with AsyncHttpClient("https://shop.test", wrap_requests_in_steps()) as client:
        json_payload_3: dict[str, JsonValue] = {"sku": "TEA-42"}
        await client.post("/orders", json=json_payload_3)

    assert_attachment(report.request_attachment).has_json_value("body.sku", "TEA-42")


async def test_attaches_async_response_body(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"delivered": True}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_1)

    async with AsyncHttpClient("https://shop.test", wrap_requests_and_responses_in_steps()) as client:
        await client.get("/orders/17")

    assert_attachment(report.response_attachment).has_json_body({"delivered": True})


async def test_attaches_only_request_when_response_not_requested(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_2: dict[str, JsonValue] = {"delivered": True}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_2)

    async with AsyncHttpClient("https://shop.test", wrap_requests_in_steps()) as client:
        await client.get("/orders/17")

    assert_report(report).has_attachments_count(1)


async def test_attaches_placeholder_for_async_streamed_response(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"m" * 8192)

    async with (
        AsyncHttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/archive.zip") as response,
    ):
        [chunk async for chunk in response.aiter_bytes()]

    assert_attachment(report.response_attachment).has_body("<streamed content>")


@pytest.mark.usefixtures("report")
async def test_delivers_full_async_streamed_body_to_caller(httpx_mock: HTTPXMock) -> None:
    payload = b"m" * 8192
    httpx_mock.add_response(status_code=codes.OK, content=payload)

    async with (
        AsyncHttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/archive.zip") as response,
    ):
        received = await response.aread()

    assert_that(received, "обертка в шаги не должна терять байты потока").is_equal_to(payload)
