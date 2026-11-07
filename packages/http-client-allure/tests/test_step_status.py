from typing import TYPE_CHECKING

import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps, wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_report

if TYPE_CHECKING:
    from .json_types import JsonValue


async def araise_for_status_inside_stream(client: AsyncHttpClient) -> None:
    async with client.stream("GET", "/feed") as response:
        await response.aread()
        response.raise_for_status()


def test_marks_step_failed_on_connection_error(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with HttpClient("https://offline.test", wrap_requests_in_steps()) as client, pytest.raises(httpx.ConnectError):
        client.get("/ping")

    assert_report(report).has_failed_step("[GET] /ping")


async def test_marks_async_step_failed_on_connection_error(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    async with AsyncHttpClient("https://offline.test", wrap_requests_in_steps()) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("/ping")

    assert_report(report).has_failed_step("[GET] /ping")


async def test_marks_async_stream_step_failed_when_caller_raises(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"error": "boom"}
    httpx_mock.add_response(status_code=codes.INTERNAL_SERVER_ERROR, json=json_payload_1)

    async with AsyncHttpClient("https://feeds.test", wrap_requests_and_responses_in_steps()) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await araise_for_status_inside_stream(client)

    assert_report(report).has_failed_step("[GET] /feed")


async def test_keeps_async_step_passed_on_success(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_2: dict[str, JsonValue] = {"ok": True}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_2)

    async with AsyncHttpClient("https://feeds.test", wrap_requests_in_steps()) as client:
        await client.get("/ping")

    assert_report(report).has_passed_step("[GET] /ping")
