from collections.abc import Iterator

import allure
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

from .assertions import assert_that

pytestmark = allure.feature("Потоковые запросы")


def read_chunks(count: int) -> Iterator[bytes]:
    """Yield the upload body in chunks, like reading a large file."""
    for number in range(count):
        yield f"chunk-{number}\n".encode()


@allure.title("Непрочитанное тело потока в отчет не выгружается")
def test_attaches_placeholder_for_unread_stream(httpbin_url: str) -> None:
    stream_size = 65536

    with (
        HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", f"/stream-bytes/{stream_size}") as response,
    ):
        received = sum(len(chunk) for chunk in response.iter_bytes())

    assert_that(received).described_as("обертка в шаг не должна терять байты потока").is_equal_to(stream_size)


@allure.title("Прочитанное внутри шага тело потока попадает в отчет")
def test_attaches_body_read_inside_step(httpbin_url: str) -> None:
    with (
        HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client,
        client.stream("GET", "/base64/aHR0cC1jbGllbnQtYWxsdXJl") as response,
    ):
        response.read()

    assert_that(response).has_text("http-client-allure")


@allure.title("send(request, stream=True) тоже оборачивается в шаг")
def test_wraps_send_with_stream_flag(httpbin_url: str) -> None:
    expected_lines = 4

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        request = client.client.build_request("GET", f"/stream/{expected_lines}")
        response = client.send(request, stream=True)
        lines = [line for line in response.iter_lines() if line]
        response.close()

    assert_that(lines).is_length(expected_lines)


@allure.title("stream_request отправляет уже собранный запрос и тоже даёт шаг")
def test_wraps_stream_request(httpbin_url: str) -> None:
    expected_lines = 6

    with HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client:
        request = client.client.build_request("GET", f"/stream/{expected_lines}")

        with client.stream_request(request) as response:
            lines = [line for line in response.iter_lines() if line]

    assert_that(lines).is_length(expected_lines)


@allure.title("Тело потоковой выгрузки не читается ради отчета")
def test_wraps_streamed_upload(httpbin_url: str) -> None:
    uploaded = "chunk-0\nchunk-1\nchunk-2\n"

    with (
        HttpClient(httpbin_url, wrap_requests_and_responses_in_steps()) as client,
        client.stream(
            "POST",
            "/anything/upload",
            content=read_chunks(3),
            headers={"content-type": "text/plain"},
        ) as response,
    ):
        response.read()

    assert_that(response).echoes_body(uploaded)
