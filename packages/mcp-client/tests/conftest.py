from __future__ import annotations

import logging
import multiprocessing
import socket
import sys
import time
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from mcp_client.connection_handlers import stdio_connection_handler, streamable_http_connection_handler

from .mock_server import serve_http

if TYPE_CHECKING:
    from collections.abc import Iterator
    from multiprocessing.process import BaseProcess

    from .support import ConnectionHandlerFactory


class ServerStartupError(RuntimeError):
    pass


@pytest.fixture(scope="session")
def mock_server_path() -> str:
    return str(Path(__file__).with_name("mock_server.py"))


@pytest.fixture(scope="session")
def http_server_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return cast("tuple[str, int]", server.getsockname())[1]


@pytest.fixture(scope="session")
def http_server_url(http_server_port: int) -> str:
    return f"http://127.0.0.1:{http_server_port}"


@pytest.fixture(scope="session")
def mcp_endpoint_url(http_server_url: str) -> str:
    return f"{http_server_url}/mcp"


@pytest.fixture(scope="session")
def http_server(http_server_port: int, mcp_endpoint_url: str) -> Iterator[BaseProcess]:
    process = multiprocessing.get_context("spawn").Process(target=serve_http, args=(http_server_port,))
    process.start()
    try:
        _wait_until_ready(process, mcp_endpoint_url)
        yield process
    finally:
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        process.close()


def _wait_until_ready(process: BaseProcess, endpoint: str) -> None:
    deadline = time.monotonic() + 15
    with httpx.Client() as client:
        while time.monotonic() < deadline:
            if not process.is_alive():
                raise ServerStartupError
            try:
                client.get(endpoint, timeout=0.5)
            except httpx.ConnectError:
                time.sleep(0.1)
            else:
                return
    raise ServerStartupError


@pytest.fixture()
def string_logger() -> Iterator[tuple[logging.Logger, StringIO]]:
    logger = logging.getLogger("mcp-test")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    with StringIO() as stream:
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        try:
            yield logger, stream
        finally:
            logger.removeHandler(handler)
            handler.close()


@pytest.fixture(params=("stdio", "http"))
def connection_handler(
    request: pytest.FixtureRequest,
    mock_server_path: str,
    http_server: BaseProcess,
    mcp_endpoint_url: str,
) -> ConnectionHandlerFactory:
    if not http_server.is_alive():
        raise ServerStartupError
    if cast("str", request.param) == "stdio":
        return stdio_connection_handler(sys.executable, [mock_server_path])
    return streamable_http_connection_handler(mcp_endpoint_url)
