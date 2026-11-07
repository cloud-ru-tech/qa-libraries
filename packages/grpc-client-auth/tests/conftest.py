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
    """Проверить готовность grpcbin настоящим gRPC вызовом.

    Открытого TCP-порта мало: контейнер успевает принять соединение раньше, чем сервис
    начинает отвечать, и первый запрос теста падает на ровном месте.
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
    """Путь к docker-compose файлу с grpcbin для тестов."""
    return [str(Path(__file__).parent / "docker-compose.yml")]


@pytest.fixture(scope="session")
def grpcbin_docker(docker_services: DockerServices, docker_ip: str) -> str:
    """Дождаться готовности тестового gRPC сервиса."""
    public_port = docker_services.port_for(_GRPCBIN_SERVICE, _GRPCBIN_PORT)
    docker_services.wait_until_responsive(timeout=60, pause=0.1, check=lambda: _check_grpcbin(docker_ip, public_port))
    return f"{docker_ip}:{public_port}"


@pytest.fixture(scope="session")
def service_addr(request: pytest.FixtureRequest) -> str:
    """Адрес сервиса grpcbin.

    Если переменная окружения SERVICE_ADDR задана — используется она, иначе поднимается контейнер.

    :return: адрес grpcbin в формате host:port
    """
    if _ENV_SERVICE_ADDR:
        return _ENV_SERVICE_ADDR
    return cast("str", request.getfixturevalue("grpcbin_docker"))


def iam_auth_response(access_token: str, expires_in: int = 3600) -> dict[str, object]:
    """Собрать тело успешного ответа сервиса IAM.

    :param access_token: токен доступа, который вернет IAM
    :param expires_in: время жизни токена в секундах
    :return: тело ответа
    """
    return {
        "access_token": access_token,
        "id_token": "id-token",
        "expires_in": expires_in,
        "scope": "test_scope",
        "token_type": "Bearer",
    }
