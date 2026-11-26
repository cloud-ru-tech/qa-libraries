from __future__ import annotations

from typing import TYPE_CHECKING, cast

import httpx2
from httpx2.websockets import WebSocketUpgradeError
from wsproto.utilities import generate_accept_token, generate_nonce

from .event_hooks import OMITTED_DEFAULT_HEADER

if TYPE_CHECKING:
    from collections.abc import Mapping


def prepare_upgrade_request(request: httpx2.Request, subprotocols: list[str] | None) -> None:
    """Set the HTTP/1.1 WebSocket upgrade headers on the prepared request.

    :param request: Request with merged client and per-call headers.
    :param subprotocols: Protocols to offer. An empty list suppresses the protocol header.
    """
    request.headers.update(
        {
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": generate_nonce().decode("ascii"),
        }
    )
    if subprotocols:
        request.headers["Sec-WebSocket-Protocol"] = ", ".join(subprotocols)
    elif subprotocols is not None:
        request.headers.pop("Sec-WebSocket-Protocol", None)
        extensions = cast("dict[str, object]", request.extensions)
        extensions[OMITTED_DEFAULT_HEADER] = "sec-websocket-protocol"


def get_upgraded_stream(response: httpx2.Response) -> object:
    """Validate the handshake and return the upgraded transport stream.

    :param response: Response to the upgrade request.
    :returns: The network stream from the response extensions.
    :raises WebSocketUpgradeError: If the upgrade failed or the network stream is missing.
    """
    if response.status_code != httpx2.codes.SWITCHING_PROTOCOLS:
        raise WebSocketUpgradeError(response)
    headers = response.headers
    request_headers = response.request.headers
    key = request_headers.get("Sec-WebSocket-Key")
    stream = cast("Mapping[str, object]", response.extensions).get("network_stream")
    selected = headers.get("Sec-WebSocket-Protocol")
    offered = request_headers.get_list("Sec-WebSocket-Protocol", split_commas=True)
    if (
        stream is None
        or headers.get("Upgrade", "").lower() != "websocket"
        or "upgrade" not in [token.lower() for token in headers.get_list("Connection", split_commas=True)]
        or not key
        or headers.get("Sec-WebSocket-Accept") != generate_accept_token(key.encode("ascii")).decode("ascii")
        or (selected is not None and selected not in offered)
        or "Sec-WebSocket-Extensions" in headers
    ):
        raise WebSocketUpgradeError(response)
    return stream
