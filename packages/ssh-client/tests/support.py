from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ssh_client import AsyncSSHClient, SyncSSHClient, options

if TYPE_CHECKING:
    from ssh_client.client import ClientOption


@dataclass(frozen=True)
class SSHTestServer:
    host: str
    port: int
    username: str
    password: str
    private_key: str
    known_hosts: str

    def sync(self, *extra: ClientOption) -> SyncSSHClient:
        return SyncSSHClient(self.host, self.port, *self._options(), *extra)

    def async_client(self, *extra: ClientOption) -> AsyncSSHClient:
        return AsyncSSHClient(self.host, self.port, *self._options(), *extra)

    def _options(self) -> tuple[ClientOption, ...]:
        return (
            options.with_password(self.username, self.password),
            options.with_known_hosts(self.known_hosts),
            options.with_request_timeout(5),
            options.with_connection_timeout(5),
        )


def connection_is_closed(client: SyncSSHClient | AsyncSSHClient) -> bool:
    if isinstance(client, SyncSSHClient):
        transport = client.client.get_transport() if client.client is not None else None
        return transport is None or not transport.is_active()
    return client.client is None or client.client.is_closed()
