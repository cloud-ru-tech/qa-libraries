from collections.abc import AsyncIterator, Iterator

import pytest
from assertpy import assert_that
from http_client import AsyncHttpClient, HttpClient
from http_client_allure import wrap_requests_in_steps
from httpx import codes
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment

TEXT_HEADERS = {"content-type": "text/plain"}


def chunks() -> Iterator[bytes]:
    yield b"first-chunk"
    yield b"second-chunk"


async def achunks() -> AsyncIterator[bytes]:
    yield b"first-chunk"
    yield b"second-chunk"


@pytest.mark.usefixtures("report")
def test_sends_whole_streamed_upload_with_curl_enabled(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://upload.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        request = client.client.build_request(
            "POST", "/blobs", content=chunks(), params={"token": "vault-key"}, headers=TEXT_HEADERS
        )
        with client.stream_request(request) as response:
            response.read()

    sent = httpx_mock.get_requests()[-1].content
    assert_that(sent, "сборка curl не должна съедать поток выгрузки до отправки").is_equal_to(
        b"first-chunksecond-chunk"
    )


def test_shows_placeholder_instead_of_streamed_upload_in_curl(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://upload.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        request = client.client.build_request(
            "POST", "/blobs", content=chunks(), params={"token": "vault-key"}, headers=TEXT_HEADERS
        )
        with client.stream_request(request) as response:
            response.read()

    assert_attachment(report.request_attachment).shows("<streamed content>")


@pytest.mark.usefixtures("report")
async def test_sends_whole_async_streamed_upload_with_curl_enabled(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    async with AsyncHttpClient("https://upload.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        request = client.client.build_request(
            "POST", "/blobs", content=achunks(), params={"token": "vault-key"}, headers=TEXT_HEADERS
        )
        async with client.stream_request(request) as response:
            await response.aread()

    sent = httpx_mock.get_requests()[-1].content
    assert_that(sent, "сборка curl не должна ломать асинхронную потоковую выгрузку").is_equal_to(
        b"first-chunksecond-chunk"
    )


def test_shows_curl_command_for_streamed_upload(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://upload.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        request = client.client.build_request(
            "POST", "/blobs", content=chunks(), params={"token": "vault-key"}, headers=TEXT_HEADERS
        )
        with client.stream_request(request) as response:
            response.read()

    assert_attachment(report.request_attachment).shows("https://upload.test/blobs")


JSON_HEADERS = {"content-type": "application/json"}


@pytest.mark.usefixtures("report")
def test_sends_streamed_json_upload_with_curl_enabled(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://upload.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        request = client.client.build_request("POST", "/events", content=chunks(), headers=JSON_HEADERS)
        with client.stream_request(request) as response:
            response.read()

    sent = httpx_mock.get_requests()[-1].content
    assert_that(sent, "сборка curl не должна падать на JSON потоке").is_equal_to(b"first-chunksecond-chunk")


def test_shows_json_safe_placeholder_in_curl(report: Report, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=codes.OK)

    with HttpClient("https://upload.test", wrap_requests_in_steps(serialize_request_to_curl=True)) as client:
        request = client.client.build_request("POST", "/events", content=chunks(), headers=JSON_HEADERS)
        with client.stream_request(request) as response:
            response.read()

    assert_attachment(report.request_attachment).shows('"<streamed content>"')
