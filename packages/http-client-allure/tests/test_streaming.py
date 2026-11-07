from typing import TYPE_CHECKING

import httpx
import pytest
from assertpy import assert_that
from http_client import AsyncHttpClient, HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment, assert_report

if TYPE_CHECKING:
    from .json_types import JsonValue


def test_wraps_stream_in_step(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"log line\n")

    with (
        HttpClient("https://logs.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/tail") as response,
    ):
        response.read()

    assert_report(report).has_single_step("[GET] /tail")


@pytest.mark.usefixtures("report")
def test_does_not_consume_streamed_response(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"z" * 2048)

    with (
        HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/dump.bin") as response,
    ):
        consumed_before_caller_read = response.is_stream_consumed

    assert_that(consumed_before_caller_read, "вложение не должно вычитывать поток за вызывающий код").is_false()


def test_attaches_placeholder_for_streamed_response(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"z" * 2048)

    with (
        HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/dump.bin") as response,
    ):
        [*response.iter_bytes()]

    assert_attachment(report.response_attachment).has_body("<streamed content>")


@pytest.mark.usefixtures("report")
def test_delivers_full_streamed_body_to_caller(httpx_mock: HTTPXMock) -> None:
    payload = b"z" * 2048
    httpx_mock.add_response(status_code=codes.OK, content=payload)

    with (
        HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/dump.bin") as response,
    ):
        received = b"".join(response.iter_bytes())

    assert_that(received, "обертка в шаги не должна терять байты потока").is_equal_to(payload)


def test_attaches_streamed_body_read_by_caller(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_1: dict[str, JsonValue] = {"cursor": "abc"}
    httpx_mock.add_response(status_code=codes.OK, json=json_payload_1)

    with (
        HttpClient("https://logs.test", wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/cursor") as response,
    ):
        response.read()

    assert_attachment(report.response_attachment).has_json_body({"cursor": "abc"})


def test_attaches_placeholder_when_sent_with_stream_flag(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK, content=b"q" * 512)

    with HttpClient("https://cdn.test", wrap_requests_and_responses_in_steps()) as client:
        request = client.client.build_request("GET", "/blob")
        response = client.send(request, stream=True)
        [*response.iter_bytes()]
        response.close()

    assert_attachment(report.response_attachment).has_body("<streamed content>")


def raise_for_status_inside_stream(client: HttpClient) -> None:
    with client.stream("GET", "/tail") as response:
        response.read()
        response.raise_for_status()


async def araise_for_status_inside_stream(client: AsyncHttpClient) -> None:
    async with client.stream("GET", "/tail") as response:
        await response.aread()
        response.raise_for_status()


def test_attaches_response_when_caller_raises_inside_stream(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_2: dict[str, JsonValue] = {"error": "boom"}
    httpx_mock.add_response(status_code=codes.INTERNAL_SERVER_ERROR, json=json_payload_2)

    with (
        HttpClient("https://logs.test", wrap_requests_and_responses_in_steps()) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        raise_for_status_inside_stream(client)

    assert_attachment(report.response_attachment).has_json_value("error", "boom")


async def test_attaches_response_when_caller_raises_inside_async_stream(report: Report, httpx_mock: HTTPXMock) -> None:
    json_payload_3: dict[str, JsonValue] = {"error": "boom"}
    httpx_mock.add_response(status_code=codes.INTERNAL_SERVER_ERROR, json=json_payload_3)

    async with AsyncHttpClient("https://logs.test", wrap_requests_and_responses_in_steps()) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await araise_for_status_inside_stream(client)

    assert_attachment(report.response_attachment).has_json_value("error", "boom")
