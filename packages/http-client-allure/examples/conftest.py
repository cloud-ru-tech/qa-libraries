from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx
import pytest


class DockerServices(Protocol):
    """Public operations for the test Docker service."""

    def port_for(self, service: str, port: int) -> int:
        """Return the service port on the Docker host."""

    def wait_until_responsive(self, *, timeout: float, pause: float, check: Callable[[], bool]) -> None:
        """Wait for a successful readiness check."""


HTTPBIN_SERVICE = "httpbin"
HTTPBIN_PORT = 8080


@pytest.fixture(scope="session")
def docker_compose_file() -> list[str]:
    """Use the demo compose file instead of the default location."""
    return [str(Path(__file__).parent / "docker-compose.yml")]


@pytest.fixture(scope="session")
def httpbin_url(docker_services: DockerServices, docker_ip: str) -> str:
    """Start httpbin and wait until it is ready.

    The ``docker_services`` fixture removes the container after the run.

    :returns: Address of the running httpbin.
    """
    public_port = docker_services.port_for(HTTPBIN_SERVICE, HTTPBIN_PORT)
    base_url = f"http://{docker_ip}:{public_port}"
    docker_services.wait_until_responsive(timeout=60, pause=0.1, check=lambda: _is_ready(base_url))
    return base_url


def _is_ready(base_url: str) -> bool:
    try:
        with httpx.Client(base_url=base_url, timeout=2) as client:
            return client.get("/status/200").status_code == httpx.codes.OK
    except httpx.HTTPError:
        return False
