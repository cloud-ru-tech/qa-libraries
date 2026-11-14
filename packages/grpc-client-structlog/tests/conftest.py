import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Protocol, cast

import grpc
import pytest
from grpc_client import ClientOption, options
from grpc_client.config import LOGGING_CONFIG

from .clients import AsyncEchoClient, EchoClient
from .fakes import StructlogRecorder, build_filtering_logger, build_stdlib_logger
from .service import CONTAINER_PORT, build_message


class DockerServices(Protocol):
    def port_for(self, service: str, port: int) -> int: ...
    def wait_until_responsive(self, *, timeout: float, pause: float, check: Callable[[], bool]) -> None: ...


class BuildClient(Protocol):
    def __call__(self, *client_options: ClientOption) -> EchoClient: ...


class BuildAsyncClient(Protocol):
    def __call__(self, *client_options: ClientOption) -> AsyncEchoClient: ...


# Service name in docker-compose.yml.
_COMPOSE_SERVICE = "echo"

# Address of an existing service. When set, no container is started.
_ENV_SERVICE_ADDR = os.getenv("SERVICE_ADDR")


def _check_service(ip: str, port: int) -> bool:
    """Check service readiness using a real gRPC call.

    An open TCP port is insufficient: the container may accept connections before the service
    starts responding, causing the first test request to fail unexpectedly.

    :param ip: container address
    :param port: exposed port
    :returns: True if the service responds to calls
    """
    try:
        with EchoClient.from_addr(f"{ip}:{port}", options.with_insecure_channel()) as client:
            return client.echo(build_message(ping=1)).status_code is grpc.StatusCode.OK
    except (OSError, grpc.RpcError):
        return False


@pytest.fixture(scope="session")
def docker_compose_file() -> list[str]:
    """Path to the docker-compose file with the test service."""
    return [str(Path(__file__).parent / "docker-compose.yml")]


@pytest.fixture(scope="session")
def service_container(docker_services: DockerServices, docker_ip: str) -> str:
    """Wait for the test gRPC service to become ready."""
    public_port = docker_services.port_for(_COMPOSE_SERVICE, CONTAINER_PORT)
    docker_services.wait_until_responsive(timeout=60, pause=0.1, check=lambda: _check_service(docker_ip, public_port))
    return f"{docker_ip}:{public_port}"


@pytest.fixture(scope="session")
def service_addr(request: pytest.FixtureRequest) -> str:
    """Address of the test gRPC service.

    Use `SERVICE_ADDR` if set; otherwise start a container.

    :returns: service address in `host:port` format
    """
    if _ENV_SERVICE_ADDR:
        return _ENV_SERVICE_ADDR
    return cast("str", request.getfixturevalue("service_container"))


@pytest.fixture()
def logger() -> StructlogRecorder:
    """Logger based on `structlog.stdlib.BoundLogger`."""
    return build_stdlib_logger()


@pytest.fixture()
def filtering_logger() -> StructlogRecorder:
    """Logger based on a class from `structlog.make_filtering_bound_logger`."""
    return build_filtering_logger()


@pytest.fixture()
def unsupported_global_log_level() -> Iterator[None]:
    """Replace the shared level setting with a value unknown to structlog."""
    original = LOGGING_CONFIG.log_level
    LOGGING_CONFIG.log_level = 15
    yield
    LOGGING_CONFIG.log_level = original


@pytest.fixture()
def build_client(service_addr: str) -> Iterator[BuildClient]:
    """Build synchronous clients and close them after the test."""
    clients: list[EchoClient] = []

    def build(*client_options: ClientOption) -> EchoClient:
        client = EchoClient.from_addr(service_addr, options.with_insecure_channel(), *client_options)
        clients.append(client)
        return client

    yield build

    for client in clients:
        client.close()


@pytest.fixture()
async def build_async_client(service_addr: str) -> AsyncIterator[BuildAsyncClient]:
    """Build asynchronous clients and close them after the test."""
    clients: list[AsyncEchoClient] = []

    def build(*client_options: ClientOption) -> AsyncEchoClient:
        client = AsyncEchoClient.from_addr(service_addr, options.with_insecure_channel(), *client_options)
        clients.append(client)
        return client

    yield build

    for client in clients:
        await client.close()
