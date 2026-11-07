"""Повтор допустим только тогда, когда тело запроса можно отправить заново.

Проверки идут через ScriptedTransport: httpx.MockTransport буферизует тело запроса
и скрывает как раз ту проблему, ради которой эти тесты написаны.
"""

import io
import pathlib
from collections.abc import AsyncIterator, Iterator
from typing import IO, TypedDict, Unpack, cast

import httpx
import pytest
from http_client import AsyncHttpClient, HttpClient
from http_client_retries.decorators import retry_if_failed
from http_client_retries.options import with_retries_failed_requests, with_retries_if
from httpx._types import RequestContent, RequestFiles

from tests.assertions import assert_that
from tests.fakes import (
    AsyncScriptedTransport,
    DisguisedStream,
    ScriptedTransport,
    UnseekableFile,
    attach_transport,
)

PAYLOAD = b"invoice-2026-03"


@pytest.fixture()
def payload_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "invoice.bin"
    path.write_bytes(PAYLOAD)

    return path


def flaky_transport() -> ScriptedTransport:
    return ScriptedTransport(httpx.ConnectError("сброс"), httpx.Response(200))


class BodyOptions(TypedDict, total=False):
    content: RequestContent
    data: dict[str, object]
    files: RequestFiles
    json: object


def send_body(transport: ScriptedTransport, **content: Unpack[BodyOptions]) -> httpx.Response:
    """Отправить запрос с указанным телом. Исключения намеренно не перехватываются."""
    with attach_transport(HttpClient("https://uploads.test", with_retries_failed_requests()), transport) as client:
        return client.send(client.client.build_request("POST", "/documents", **content))


@pytest.mark.usefixtures("fast_retries")
def test_repeats_request_with_bytes_body() -> None:
    transport = flaky_transport()

    send_body(transport, content=PAYLOAD)

    assert_that(transport.bodies).is_equal_to([PAYLOAD, PAYLOAD])


@pytest.mark.usefixtures("fast_retries")
def test_repeats_request_with_json_body() -> None:
    transport = flaky_transport()

    send_body(transport, json=dict[str, object]({"number": "2026-03"}))

    assert_that(transport.bodies[0]).is_equal_to(transport.bodies[1])


@pytest.mark.usefixtures("fast_retries")
def test_rewinds_file_body_before_repeating(payload_file: pathlib.Path) -> None:
    transport = flaky_transport()

    with payload_file.open("rb") as handle:
        send_body(transport, content=handle)

    assert_that(transport.bodies).is_equal_to([PAYLOAD, PAYLOAD])


@pytest.mark.usefixtures("fast_retries")
def test_repeats_multipart_body_with_seekable_file(payload_file: pathlib.Path) -> None:
    transport = flaky_transport()

    with payload_file.open("rb") as handle:
        send_body(transport, files={"document": handle})

    assert_that(transport.bodies[0]).is_equal_to(transport.bodies[1])


@pytest.mark.usefixtures("fast_retries")
def test_does_not_repeat_multipart_body_with_unseekable_file() -> None:
    transport = flaky_transport()

    with pytest.raises(httpx.ConnectError):
        send_body(transport, files={"document": cast("IO[bytes]", UnseekableFile(PAYLOAD))})

    assert_that(transport.attempts).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
def test_never_repeats_multipart_body_without_its_file() -> None:
    transport = flaky_transport()

    with pytest.raises(httpx.ConnectError):
        send_body(transport, files={"document": cast("IO[bytes]", UnseekableFile(PAYLOAD))})

    assert_that([body for body in transport.bodies if PAYLOAD not in body]).is_empty()


@pytest.mark.usefixtures("fast_retries")
def test_does_not_repeat_request_with_generator_body() -> None:
    transport = flaky_transport()

    def stream_document() -> Iterator[bytes]:
        yield b"page-1"
        yield b"page-2"

    with pytest.raises(httpx.ConnectError):
        send_body(transport, content=stream_document())

    assert_that(transport.attempts).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
def test_reports_original_error_for_generator_body() -> None:
    transport = flaky_transport()

    def stream_document() -> Iterator[bytes]:
        yield b"page-1"

    with pytest.raises(httpx.ConnectError):
        send_body(transport, content=stream_document())


@pytest.mark.usefixtures("fast_retries")
def test_rewinds_file_body_for_streaming_send(payload_file: pathlib.Path) -> None:
    transport = flaky_transport()

    with (
        attach_transport(HttpClient("https://uploads.test", with_retries_failed_requests()), transport) as client,
        payload_file.open("rb") as handle,
    ):
        client.send(client.client.build_request("POST", "/documents", content=handle), stream=True)

    assert_that(transport.bodies).is_equal_to([PAYLOAD, PAYLOAD])


@pytest.mark.usefixtures("fast_retries")
def test_rewinds_file_body_for_stream_request(payload_file: pathlib.Path) -> None:
    transport = flaky_transport()

    with (
        attach_transport(HttpClient("https://uploads.test", with_retries_failed_requests()), transport) as client,
        payload_file.open("rb") as handle,
        client.stream_request(client.client.build_request("POST", "/documents", content=handle)),
    ):
        pass

    assert_that(transport.bodies).is_equal_to([PAYLOAD, PAYLOAD])


@pytest.mark.usefixtures("fast_retries")
async def test_repeats_multipart_body_on_async_client(payload_file: pathlib.Path) -> None:
    transport = AsyncScriptedTransport(httpx.ConnectError("сброс"), httpx.Response(200))

    async with attach_transport(
        AsyncHttpClient("https://uploads.test", with_retries_failed_requests()), transport
    ) as client:
        with payload_file.open("rb") as handle:
            await client.send(client.client.build_request("POST", "/documents", files={"document": handle}))

    assert_that(transport.bodies[0]).is_equal_to(transport.bodies[1])


@pytest.mark.usefixtures("fast_retries")
async def test_does_not_repeat_multipart_body_with_unseekable_file_on_async_client() -> None:
    transport = AsyncScriptedTransport(httpx.ConnectError("сброс"), httpx.Response(200))

    async with attach_transport(
        AsyncHttpClient("https://uploads.test", with_retries_failed_requests()), transport
    ) as client:
        with pytest.raises(httpx.ConnectError):
            await client.send(
                client.client.build_request(
                    "POST", "/documents", files={"document": cast("IO[bytes]", UnseekableFile(PAYLOAD))}
                )
            )

    assert_that(transport.attempts).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
async def test_does_not_repeat_generator_body_on_async_client() -> None:
    transport = AsyncScriptedTransport(httpx.ConnectError("сброс"), httpx.Response(200))

    async def stream_document() -> AsyncIterator[bytes]:
        yield b"page-1"

    async with attach_transport(
        AsyncHttpClient("https://uploads.test", with_retries_failed_requests()), transport
    ) as client:
        with pytest.raises(httpx.ConnectError):
            await client.send(client.client.build_request("POST", "/documents", content=stream_document()))

    assert_that(transport.attempts).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
def test_checks_condition_once_when_body_cannot_be_repeated() -> None:
    transport = ScriptedTransport(httpx.Response(503))
    checks: list[int] = []

    def is_server_error(response: httpx.Response) -> bool:
        checks.append(response.status_code)

        return response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR

    def stream_document() -> Iterator[bytes]:
        yield b"page-1"

    with attach_transport(HttpClient("https://uploads.test", with_retries_if(is_server_error)), transport) as client:
        client.send(client.client.build_request("POST", "/documents", content=stream_document()))

    assert_that(checks).is_equal_to([503])


@pytest.mark.usefixtures("fast_retries")
def test_returns_rejected_response_when_body_cannot_be_repeated() -> None:
    transport = ScriptedTransport(httpx.Response(503))

    def stream_document() -> Iterator[bytes]:
        yield b"page-1"

    with attach_transport(
        HttpClient(
            "https://uploads.test",
            with_retries_if(lambda response: response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR),
        ),
        transport,
    ) as client:
        response = client.send(client.client.build_request("POST", "/documents", content=stream_document()))

    assert_that(response.status_code).is_equal_to(503)


@pytest.mark.usefixtures("fast_retries")
def test_repeats_multipart_body_given_as_bytes() -> None:
    transport = flaky_transport()

    send_body(transport, files={"document": ("invoice.bin", PAYLOAD)})

    assert_that(transport.bodies[0]).is_equal_to(transport.bodies[1])


@pytest.mark.usefixtures("fast_retries")
def test_repeats_body_given_as_sequence_of_chunks() -> None:
    transport = flaky_transport()

    send_body(transport, content=[b"invoice-", b"2026-03"])

    assert_that(transport.bodies).is_equal_to([PAYLOAD, PAYLOAD])


@pytest.mark.usefixtures("fast_retries")
def test_does_not_repeat_unknown_stream_type() -> None:
    transport = flaky_transport()

    with (
        pytest.raises(httpx.ConnectError),
        attach_transport(HttpClient("https://uploads.test", with_retries_failed_requests()), transport) as client,
    ):
        client.send(httpx.Request("POST", "https://uploads.test/documents", stream=DisguisedStream(PAYLOAD)))

    assert_that(transport.attempts).is_equal_to(1)


@pytest.mark.usefixtures("fast_retries")
def test_rewinds_body_when_request_passed_under_any_keyword() -> None:
    attempts: list[bytes] = []

    def endpoint(req: httpx.Request) -> httpx.Response:
        attempts.append(b"".join(cast("httpx.SyncByteStream", req.stream)))
        if len(attempts) == 1:
            message = "сброс"
            raise httpx.ConnectError(message, request=req)

        return httpx.Response(200)

    retry_if_failed(endpoint)(req=httpx.Request("POST", "https://uploads.test/x", content=io.BytesIO(PAYLOAD)))

    assert_that(attempts).is_equal_to([PAYLOAD, PAYLOAD])


@pytest.mark.usefixtures("fast_retries")
def test_keeps_original_error_object_for_generator_body() -> None:
    failure = httpx.ConnectError("сброс")
    transport = ScriptedTransport(failure, httpx.Response(200))

    def stream_document() -> Iterator[bytes]:
        yield b"page-1"

    with pytest.raises(httpx.ConnectError) as raised:
        send_body(transport, content=stream_document())

    assert_that(raised.value).is_same_as(failure)
