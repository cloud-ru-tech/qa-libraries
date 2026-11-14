import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import grpc
import pytest
from api import grpcbin_pb2

from .clients.grpcbin import GRPCbinServiceClient


class DockerServices(Protocol):
    def port_for(self, service: str, port: int) -> int: ...
    def wait_until_responsive(self, *, timeout: float, pause: float, check: Callable[[], bool]) -> None: ...


IAM_URL = "https://iam-api.example.com"

_GRPCBIN_PORT = 9000
_GRPCBIN_SERVICE = "grpcbin"
_ENV_SERVICE_ADDR = os.getenv("SERVICE_ADDR")


def _check_grpcbin(ip: str, port: int) -> bool:
    """Check grpcbin readiness using a real gRPC call.

    An open TCP port is insufficient: the container may accept connections before the service
    starts responding, causing the first test request to fail unexpectedly.
    """
    try:
        with socket.create_connection((ip, port), timeout=1), grpc.insecure_channel(f"{ip}:{port}") as channel:
            cast("grpc.Future[object]", grpc.channel_ready_future(channel)).result(timeout=2)
            stub = GRPCbinServiceClient.from_channel(channel).stub
            stub.HeadersUnary(grpcbin_pb2.EmptyMessage(), timeout=2)
            return True
    except (OSError, grpc.RpcError, grpc.FutureTimeoutError):
        return False


@pytest.fixture(scope="session")
def docker_compose_file() -> list[str]:
    """Path to the docker-compose file with grpcbin for tests."""
    return [str(Path(__file__).parent / "docker-compose.yml")]


@pytest.fixture(scope="session")
def grpcbin_docker(docker_services: DockerServices, docker_ip: str) -> str:
    """Wait for the test gRPC service to become ready."""
    public_port = docker_services.port_for(_GRPCBIN_SERVICE, _GRPCBIN_PORT)
    docker_services.wait_until_responsive(timeout=60, pause=0.1, check=lambda: _check_grpcbin(docker_ip, public_port))
    return f"{docker_ip}:{public_port}"


@pytest.fixture(scope="session")
def service_addr(request: pytest.FixtureRequest) -> str:
    """Address of the grpcbin service.

    Use the SERVICE_ADDR environment variable if set; otherwise start a container.

    :return: grpcbin address in host:port format
    """
    if _ENV_SERVICE_ADDR:
        return _ENV_SERVICE_ADDR
    return cast("str", request.getfixturevalue("grpcbin_docker"))


def iam_auth_response(access_token: str, expires_in: int = 3600) -> dict[str, object]:
    """Build a successful IAM service response body.

    :param access_token: access token returned by IAM
    :param expires_in: token lifetime in seconds
    :return: response body
    """
    return {
        "access_token": access_token,
        "id_token": "id-token",
        "expires_in": expires_in,
        "scope": "test_scope",
        "token_type": "Bearer",
    }
