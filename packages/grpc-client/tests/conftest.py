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


@pytest.fixture()
def boe_client(service_addr: str) -> Iterator[ABitOfEverythingServiceClient]:
    """Client for the A Bit Of Everything service."""
    with ABitOfEverythingServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        yield client


@pytest.fixture()
def grpcbin_client(service_addr: str) -> Iterator[GRPCbinServiceClient]:
    """Client for the grpcbin service."""
    with GRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        yield client


@pytest.fixture()
async def async_grpcbin_client(service_addr: str) -> AsyncIterator[AsyncGRPCbinServiceClient]:
    """Asynchronous client for the grpcbin service."""
    async with AsyncGRPCbinServiceClient.from_addr(service_addr, options.with_insecure_channel()) as client:
        yield client


@pytest.fixture()
def dummy_message(faker: Faker) -> grpcbin_pb2.DummyMessage:
    """Test message with random contents."""
    return _generate_dummy_msg(faker)


@pytest.fixture()
def dummy_messages(faker: Faker) -> Iterator[grpcbin_pb2.DummyMessage]:
    """Stream of ten test messages."""

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
    """Stream used by the test logger."""
    return io.StringIO()


@pytest.fixture()
def logger(log_stream: io.StringIO, request: pytest.FixtureRequest) -> Iterator[logging.Logger]:
    """Logger that writes to a separate stream for each test."""
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
