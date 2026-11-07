import io
import logging
import os
import socket
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Protocol, cast

import grpc
import pytest
from api import grpcbin_pb2
from faker import Faker
from grpc_client import options

from .clients import ABitOfEverythingServiceClient, AsyncGRPCbinServiceClient, GRPCbinServiceClient


class DockerServices(Protocol):
    def port_for(self, service: str, port: int) -> int: ...
    def wait_until_responsive(self, *, timeout: float, pause: float, check: Callable[[], bool]) -> None: ...


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


@pytest.fixture()
def boe_client(service_addr: str) -> Iterator[ABitOfEverythingServiceClient]:
    """Клиент сервиса «A Bit Of Everything»."""
    with ABitOfEverythingServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        yield client


@pytest.fixture()
def grpcbin_client(service_addr: str) -> Iterator[GRPCbinServiceClient]:
    """Клиент сервиса grpcbin."""
    with GRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        yield client


@pytest.fixture()
async def async_grpcbin_client(service_addr: str) -> AsyncIterator[AsyncGRPCbinServiceClient]:
    """Асинхронный клиент сервиса grpcbin."""
    async with AsyncGRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        yield client


@pytest.fixture()
def dummy_message(faker: Faker) -> grpcbin_pb2.DummyMessage:
    """Тестовое сообщение со случайным содержимым."""
    return _generate_dummy_msg(faker)


@pytest.fixture()
def dummy_messages(faker: Faker) -> Iterator[grpcbin_pb2.DummyMessage]:
    """Поток из десяти тестовых сообщений."""

    def iterator() -> Iterator[grpcbin_pb2.DummyMessage]:
        for _ in range(10):
            yield _generate_dummy_msg(faker)

    return iterator()


def _generate_dummy_msg(faker: Faker) -> grpcbin_pb2.DummyMessage:
    def generate_sub() -> grpcbin_pb2.DummyMessage.Sub:
        return grpcbin_pb2.DummyMessage.Sub(f_string=faker.word())

    return grpcbin_pb2.DummyMessage(
        f_string=faker.sentence(),
        f_strings=[faker.word() for _ in range(faker.random_int(2, 5))],
        f_int32=faker.pyint(),
        f_int32s=[faker.pyint() for _ in range(faker.random_int(2, 5))],
        f_enum=faker.random_element(elements=tuple(grpcbin_pb2.DummyMessage.Enum.keys())),
        f_enums=[
            faker.random_element(elements=tuple(grpcbin_pb2.DummyMessage.Enum.keys()))
            for _ in range(faker.random_int(2, 5))
        ],
        f_sub=generate_sub(),
        f_subs=[generate_sub() for _ in range(faker.random_int(2, 5))],
        f_bool=faker.boolean(),
        f_bools=[faker.boolean() for _ in range(faker.random_int(2, 5))],
        f_int64=faker.pyint(),
        f_int64s=[faker.pyint() for _ in range(faker.random_int(2, 5))],
        f_bytes=faker.binary(length=faker.random_int(2, 20)),
        f_bytess=[faker.binary(length=faker.random_int(2, 20)) for _ in range(faker.random_int(2, 5))],
        f_float=faker.pyfloat(),
        f_floats=[faker.pyfloat() for _ in range(faker.random_int(2, 5))],
    )


@pytest.fixture()
def log_stream() -> io.StringIO:
    """Поток, в который пишет тестовый логгер."""
    return io.StringIO()


@pytest.fixture()
def logger(log_stream: io.StringIO, request: pytest.FixtureRequest) -> Iterator[logging.Logger]:
    """Логгер, пишущий в отдельный поток для каждого теста."""
    item = cast("pytest.Item", request.node)
    log = logging.getLogger(f"grpc_client_test.{item.name}")
    log.setLevel(logging.DEBUG)
    log.propagate = False

    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)

    yield log

    log.removeHandler(handler)
    handler.close()
