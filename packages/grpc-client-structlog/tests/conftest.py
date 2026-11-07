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


# Имя сервиса в docker-compose.yml.
_COMPOSE_SERVICE = "echo"

# Адрес уже поднятого сервиса. Задан — контейнер не поднимается.
_ENV_SERVICE_ADDR = os.getenv("SERVICE_ADDR")


def _check_service(ip: str, port: int) -> bool:
    """Проверить готовность сервиса настоящим gRPC вызовом.

    Открытого TCP-порта мало: контейнер успевает принять соединение раньше, чем сервис
    начинает отвечать, и первый запрос теста падает на ровном месте.

    :param ip: адрес контейнера
    :param port: порт, проброшенный наружу
    :returns: True, если сервис отвечает на вызовы
    """
    try:
        with EchoClient.from_addr(f"{ip}:{port}", options.with_insecure_channel()) as client:
            return client.echo(build_message(ping=1)).status_code is grpc.StatusCode.OK
    except (OSError, grpc.RpcError):
        return False


@pytest.fixture(scope="session")
def docker_compose_file() -> list[str]:
    """Путь к docker-compose файлу с тестовым сервисом."""
    return [str(Path(__file__).parent / "docker-compose.yml")]


@pytest.fixture(scope="session")
def service_container(docker_services: DockerServices, docker_ip: str) -> str:
    """Дождаться готовности тестового gRPC сервиса."""
    public_port = docker_services.port_for(_COMPOSE_SERVICE, CONTAINER_PORT)
    docker_services.wait_until_responsive(timeout=60, pause=0.1, check=lambda: _check_service(docker_ip, public_port))
    return f"{docker_ip}:{public_port}"


@pytest.fixture(scope="session")
def service_addr(request: pytest.FixtureRequest) -> str:
    """Адрес тестового gRPC сервиса.

    Переменная `SERVICE_ADDR` задана — используется она, иначе поднимается контейнер.

    :returns: адрес сервиса вида `host:port`
    """
    if _ENV_SERVICE_ADDR:
        return _ENV_SERVICE_ADDR
    return cast("str", request.getfixturevalue("service_container"))


@pytest.fixture()
def logger() -> StructlogRecorder:
    """Логгер на основе `structlog.stdlib.BoundLogger`."""
    return build_stdlib_logger()


@pytest.fixture()
def filtering_logger() -> StructlogRecorder:
    """Логгер на основе класса из `structlog.make_filtering_bound_logger`."""
    return build_filtering_logger()


@pytest.fixture()
def unsupported_global_log_level() -> Iterator[None]:
    """Подменить общую настройку уровня на значение, которого structlog не знает."""
    original = LOGGING_CONFIG.log_level
    LOGGING_CONFIG.log_level = 15
    yield
    LOGGING_CONFIG.log_level = original


@pytest.fixture()
def build_client(service_addr: str) -> Iterator[BuildClient]:
    """Фабрика синхронных клиентов, закрывающая их после теста."""
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
    """Фабрика асинхронных клиентов, закрывающая их после теста."""
    clients: list[AsyncEchoClient] = []

    def build(*client_options: ClientOption) -> AsyncEchoClient:
        client = AsyncEchoClient.from_addr(service_addr, options.with_insecure_channel(), *client_options)
        clients.append(client)
        return client

    yield build

    for client in clients:
        await client.close()
