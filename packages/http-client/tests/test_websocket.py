from collections.abc import Awaitable, Iterator
from threading import Thread
from typing import TYPE_CHECKING, cast

import httpx2
import pytest
from assertpy import assert_that
from http_client.options import with_auth, with_default_headers
from httpx2.websockets import WebSocketDisconnect, WebSocketUpgradeError
from pytest_httpx2 import HTTPXMock
from wsproto.utilities import generate_accept_token

from .support.clients import AsyncClientFactory, SyncClientFactory
from .support.websocket import WebSocketServer

if TYPE_CHECKING:
    from http_client.types import WebSocketOptions

INVALID_UPGRADES = (
    ("Connection", None),
    ("Upgrade", None),
    ("Sec-WebSocket-Accept", None),
    ("Sec-WebSocket-Accept", "wrong"),
    ("Sec-WebSocket-Protocol", "unoffered"),
    ("Sec-WebSocket-Extensions", "permessage-deflate"),
    pytest.param(None, None, id="missing-network-stream"),
)


@pytest.fixture()
def ws_server() -> Iterator[WebSocketServer]:
    with WebSocketServer() as server:
        thread = Thread(target=server.serve_forever, args=(0.01,), daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


def test_websocket_exchanges_messages_in_order(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url)
    payload = {"result": "ready"}

    with client.websocket("/ws") as session:
        session.send_text("progress")
        text = session.receive_text(timeout=3)
        session.send_bytes(b"\x00\xff")
        binary = session.receive_bytes(timeout=3)
        session.send_json(payload)
        result = cast("object", session.receive_json(timeout=3))

    assert_that((text, binary, result)).is_equal_to(("progress", b"\x00\xff", payload))


async def test_async_websocket_exchanges_messages_in_order(
    ws_server: WebSocketServer,
    new_async_client: AsyncClientFactory,
) -> None:
    client = new_async_client(ws_server.url)
    payload = {"result": "ready"}

    async with client.websocket("/ws") as session:
        await session.send_text("progress")
        text = await session.receive_text(timeout=3)
        await session.send_bytes(b"\x00\xff")
        binary = await session.receive_bytes(timeout=3)
        await session.send_json(payload)
        result = await cast("Awaitable[object]", session.receive_json(timeout=3))

    assert_that((text, binary, result)).is_equal_to(("progress", b"\x00\xff", payload))


def test_websocket_closes_on_consumer_error(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url)

    with pytest.raises(_ConsumerError), client.websocket("/ws"):
        raise _ConsumerError

    assert_that(ws_server.close_codes.get(timeout=3)).is_equal_to(1000)


async def test_async_websocket_closes_on_consumer_error(
    ws_server: WebSocketServer, new_async_client: AsyncClientFactory
) -> None:
    client = new_async_client(ws_server.url)

    with pytest.RaisesGroup(_ConsumerError, allow_unwrapped=True):
        async with client.websocket("/ws"):
            raise _ConsumerError

    assert_that(ws_server.close_codes.get(timeout=3)).is_equal_to(1000)


def test_websocket_applies_message_size_limit(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url)

    with client.websocket("/ws", max_message_size_bytes=4) as session:
        session.send_bytes(b"12345")
        with pytest.raises(WebSocketDisconnect) as error:
            session.receive_bytes(timeout=3)

    assert_that(error.value.code).is_equal_to(1009)


async def test_async_websocket_applies_message_size_limit(
    ws_server: WebSocketServer,
    new_async_client: AsyncClientFactory,
) -> None:
    client = new_async_client(ws_server.url)

    async with client.websocket("/ws", max_message_size_bytes=4) as session:
        await session.send_bytes(b"12345")
        with pytest.raises(WebSocketDisconnect) as error:
            await session.receive_bytes(timeout=3)

    assert_that(error.value.code).is_equal_to(1009)


def test_websocket_negotiates_requested_subprotocol(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url)

    with client.websocket("/ws", subprotocols=["updates"]) as session:
        assert_that(session.subprotocol).is_equal_to("updates")


@pytest.mark.parametrize("anonymous", [False, True])
def test_websocket_applies_handshake_options(
    ws_server: WebSocketServer,
    new_client: SyncClientFactory,
    *,
    anonymous: bool,
) -> None:
    client = new_client(ws_server.url, with_auth(_authorize), with_default_headers({"X-Client": "qa"}))

    with client.websocket("/ws", params={"topic": "checks"}, headers={"X-Channel": "events"}, anonymous=anonymous):
        _assert_handshake(ws_server, anonymous=anonymous)


@pytest.mark.parametrize("anonymous", [False, True])
async def test_async_websocket_applies_handshake_options(
    ws_server: WebSocketServer,
    new_async_client: AsyncClientFactory,
    *,
    anonymous: bool,
) -> None:
    client = new_async_client(ws_server.url, with_auth(_authorize), with_default_headers({"X-Client": "qa"}))

    async with client.websocket(
        "/ws", params={"topic": "checks"}, headers={"X-Channel": "events"}, anonymous=anonymous
    ):
        _assert_handshake(ws_server, anonymous=anonymous)


def test_websocket_rejects_a_handshake_body(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url)
    options = cast("WebSocketOptions", {"content": b"build"})

    with pytest.raises(TypeError, match="content"), client.websocket("/ws", **options):
        pass


def test_websocket_reports_refused_upgrade(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url)

    with pytest.raises(WebSocketUpgradeError) as error, client.websocket("/denied"):
        pytest.fail("The server refused the upgrade")

    assert_that(error.value.response.status_code).is_equal_to(403)


def test_empty_subprotocol_list_offers_no_protocol(ws_server: WebSocketServer, new_client: SyncClientFactory) -> None:
    client = new_client(ws_server.url, with_default_headers({"sec-websocket-protocol": "fallback"}))

    with client.websocket("/ws", headers={"Sec-WebSocket-Protocol": "old"}, subprotocols=[]):
        assert_that(ws_server.handshakes.get(timeout=3).subprotocols).is_empty()


@pytest.mark.parametrize(("subprotocols", "expected"), [(None, "fallback"), ([], None), (["events"], "events")])
async def test_async_websocket_call_controls_default_subprotocol(
    ws_server: WebSocketServer,
    new_async_client: AsyncClientFactory,
    subprotocols: list[str] | None,
    expected: str | None,
) -> None:
    client = new_async_client(ws_server.url, with_default_headers({"Sec-WebSocket-Protocol": "fallback"}))

    async with client.websocket("/ws", subprotocols=subprotocols) as session:
        assert_that(session.subprotocol).is_equal_to(expected)


async def test_async_websocket_reports_refused_upgrade(
    ws_server: WebSocketServer, new_async_client: AsyncClientFactory
) -> None:
    client = new_async_client(ws_server.url)

    with pytest.raises(WebSocketUpgradeError) as error:
        async with client.websocket("/denied"):
            pytest.fail("The server refused the upgrade")

    assert_that(error.value.response.status_code).is_equal_to(403)


@pytest.mark.parametrize(("header", "value"), INVALID_UPGRADES)
def test_websocket_rejects_invalid_upgrade(
    httpx2_mock: HTTPXMock,
    new_client: SyncClientFactory,
    header: str | None,
    value: str | None,
) -> None:
    response = _mock_invalid_upgrade(httpx2_mock, header, value)
    client = new_client("http://example.com")

    with pytest.raises(WebSocketUpgradeError) as error, client.websocket("/ws", subprotocols=["updates"]):
        pytest.fail("The client accepted invalid upgrade headers")

    assert_that(error.value.response).is_same_as(response)


@pytest.mark.parametrize(("header", "value"), INVALID_UPGRADES)
async def test_async_websocket_rejects_invalid_upgrade(
    httpx2_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
    header: str | None,
    value: str | None,
) -> None:
    response = _mock_invalid_upgrade(httpx2_mock, header, value)
    client = new_async_client("http://example.com")

    with pytest.raises(WebSocketUpgradeError) as error:
        async with client.websocket("/ws", subprotocols=["updates"]):
            pytest.fail("The client accepted invalid upgrade headers")

    assert_that(error.value.response).is_same_as(response)


def _mock_invalid_upgrade(httpx2_mock: HTTPXMock, header: str | None, value: str | None) -> httpx2.Response:
    extensions = {"network_stream": object()} if header is not None else {}
    response = httpx2.Response(101, headers={"Connection": "Upgrade", "Upgrade": "websocket"}, extensions=extensions)

    def handshake(request: httpx2.Request) -> httpx2.Response:
        key = request.headers["Sec-WebSocket-Key"].encode("ascii")
        response.headers["Sec-WebSocket-Accept"] = generate_accept_token(key).decode("ascii")
        if header is None:
            return response
        if value is None:
            del response.headers[header]
        else:
            response.headers[header] = value
        return response

    httpx2_mock.add_callback(handshake)
    return response


def _authorize(request: httpx2.Request) -> httpx2.Request:
    request.headers["Authorization"] = "Test qa"
    return request


def _assert_handshake(server: WebSocketServer, *, anonymous: bool) -> None:
    request = server.handshakes.get(timeout=3)
    headers = httpx2.Headers(request.extra_headers)
    assert_that(request.target).is_equal_to("/ws?topic=checks")
    assert_that(headers["X-Client"]).is_equal_to("qa")
    assert_that(headers["X-Channel"]).is_equal_to("events")
    assert_that(headers.get("Authorization")).is_equal_to(None if anonymous else "Test qa")


class _ConsumerError(Exception):
    pass
