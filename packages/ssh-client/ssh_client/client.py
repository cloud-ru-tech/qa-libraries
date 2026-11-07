from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from copy import copy, deepcopy
from typing import TYPE_CHECKING, Self, Unpack, cast

from .config import SSHClientConfig

if TYPE_CHECKING:
    from types import TracebackType

    from .results import LiveSSHResult, SSHResult
    from .types import (
        AsyncCloseable,
        Closeable,
        ExecuteOptions,
        LiveExecuteOptions,
        OperationDecorator,
        OutputCallback,
        RequestHook,
        ResponseHook,
    )
    from .utils.retries import RetryPolicy

type ClientOption = Callable[["InitSSHClient"], None]


class InitSSHClient:
    """Configure SSH clients through built-in and custom options."""

    DEFAULT_TIMEOUT = 30

    def __init__(self, host: str, port: int = 22, *options: ClientOption) -> None:
        """Apply options to this client.

        :param host: SSH server hostname.
        :param port: SSH server port.
        :param options: Options receiving the actual client instance.
        """
        self.host = host
        self.port = port
        self._config = SSHClientConfig(timeout=self.DEFAULT_TIMEOUT)
        self._request_hooks: list[RequestHook] = []
        self._response_hooks: list[ResponseHook] = []
        self._connect_decorators: list[OperationDecorator] = []
        self._execute_decorators: list[OperationDecorator] = []
        for option in options:
            option(self)

    @property
    def username(self) -> str | None:
        """Return the configured username."""
        return self._config.username

    @username.setter
    def username(self, value: str | None) -> None:
        """Set the username.

        :param value: New client setting.
        """
        self._config.username = value

    @property
    def password(self) -> str | None:
        """Return the configured password."""
        return self._config.password

    @password.setter
    def password(self, value: str | None) -> None:
        """Set the password.

        :param value: New client setting.
        """
        self._config.password = value

    @property
    def private_key_path(self) -> str | None:
        """Return the configured private key path."""
        return self._config.private_key_path

    @private_key_path.setter
    def private_key_path(self, value: str | None) -> None:
        """Set the private key path.

        :param value: New client setting.
        """
        self._config.private_key_path = value

    @property
    def known_hosts(self) -> str | None:
        """Return the configured known hosts."""
        return self._config.known_hosts

    @known_hosts.setter
    def known_hosts(self, value: str | None) -> None:
        """Set the known hosts.

        :param value: New client setting.
        """
        self._config.known_hosts = value

    @property
    def timeout(self) -> float:
        """Return the configured timeout."""
        return self._config.timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        """Set the timeout.

        :param value: New client setting.
        """
        self._config.timeout = value

    @property
    def connection_timeout(self) -> float | None:
        """Return the configured connection timeout."""
        return self._config.connection_timeout

    @connection_timeout.setter
    def connection_timeout(self, value: float | None) -> None:
        """Set the connection timeout.

        :param value: New client setting.
        """
        self._config.connection_timeout = value

    @property
    def connection_retry(self) -> RetryPolicy | None:
        """Return the configured connection retry."""
        return self._config.connection_retry

    @connection_retry.setter
    def connection_retry(self, value: RetryPolicy | None) -> None:
        """Set the connection retry.

        :param value: New client setting.
        """
        self._config.connection_retry = value

    @property
    def command_retry(self) -> RetryPolicy | None:
        """Return the configured command retry."""
        return self._config.command_retry

    @command_retry.setter
    def command_retry(self, value: RetryPolicy | None) -> None:
        """Set the command retry.

        :param value: New client setting.
        """
        self._config.command_retry = value

    @property
    def live_stdout_callback(self) -> OutputCallback | None:
        """Return the configured live stdout callback."""
        return self._config.live_stdout_callback

    @live_stdout_callback.setter
    def live_stdout_callback(self, value: OutputCallback | None) -> None:
        """Set the live stdout callback.

        :param value: New client setting.
        """
        self._config.live_stdout_callback = value

    @property
    def live_stderr_callback(self) -> OutputCallback | None:
        """Return the configured live stderr callback."""
        return self._config.live_stderr_callback

    @live_stderr_callback.setter
    def live_stderr_callback(self, value: OutputCallback | None) -> None:
        """Set the live stderr callback.

        :param value: New client setting.
        """
        self._config.live_stderr_callback = value

    def add_request_hook(self, hook: RequestHook) -> None:
        """Register a request observer.

        :param hook: Request callback.
        """
        self._request_hooks.append(hook)

    def add_response_hook(self, hook: ResponseHook) -> None:
        """Register a response observer.

        :param hook: Response callback.
        """
        self._response_hooks.append(hook)

    def add_connect_decorator(self, decorator: OperationDecorator) -> None:
        """Register a connection wrapper.

        :param decorator: Operation-preserving decorator.
        """
        self._connect_decorators.append(decorator)

    def add_execute_decorator(self, decorator: OperationDecorator) -> None:
        """Register a command wrapper.

        :param decorator: Operation-preserving decorator.
        """
        self._execute_decorators.append(decorator)

    def with_options(self, *temp_options: ClientOption) -> Self:
        """Create a disconnected copy with independent settings and hooks.

        :param temp_options: Options overriding the copied settings.
        :return: Independent client of the same type.
        """
        temporary = copy(self)
        for option in temp_options:
            option(temporary)
        return temporary

    def __copy__(self) -> Self:
        """Copy options without copying live transport resources."""
        temporary = type(self).__new__(type(self))
        cast("dict[str, object]", temporary.__dict__).update(
            {
                **cast("dict[str, object]", self.__dict__),
                "_config": deepcopy(self._config),
                "_client": None,
                "_connected": False,
                "_request_hooks": self._request_hooks.copy(),
                "_response_hooks": self._response_hooks.copy(),
                "_connect_decorators": self._connect_decorators.copy(),
                "_execute_decorators": self._execute_decorators.copy(),
            }
        )
        return temporary

    def _request(self, command: str) -> None:
        for hook in self._request_hooks:
            hook(host=self.host, port=self.port, username=self.username, command=command)

    def _response(self, command: str, result: SSHResult | LiveSSHResult) -> None:
        for hook in self._response_hooks:
            hook(host=self.host, command=command, result=result)

    def _decorate[T](self, operation: Callable[[], T], decorators: list[OperationDecorator]) -> Callable[[], T]:
        for decorator in reversed(decorators):
            operation = decorator(operation)
        return operation


class BaseSSHClient[ConnectionT: Closeable](InitSSHClient, ABC):
    """Manage the lifetime of a synchronous SSH transport."""

    def __init__(self, host: str, port: int = 22, *options: ClientOption) -> None:
        """Configure the client without opening a connection.

        :param host: SSH server hostname.
        :param port: SSH server port.
        :param options: Client options.
        """
        self._client: ConnectionT | None = None
        self._connected = False
        super().__init__(host, port, *options)

    @property
    def client(self) -> ConnectionT | None:
        """Return the most recently created transport."""
        return self._client

    def __enter__(self) -> Self:
        """Return this client for scoped cleanup."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Release the transport on context exit."""
        self.close()

    def close(self) -> None:
        """Close active and partially opened transports."""
        if self._client is not None:
            self._client.close()
        self._connected = False

    @abstractmethod
    def connect(self) -> None:
        """Open an authenticated connection."""
        ...

    @abstractmethod
    def execute(self, command: str | list[str], **options: Unpack[ExecuteOptions]) -> SSHResult:
        """Run a command and collect stdout and stderr."""
        ...

    @abstractmethod
    def execute_live(self, command: str | list[str], **options: Unpack[LiveExecuteOptions]) -> LiveSSHResult:
        """Run a command while emitting output lines."""
        ...


class BaseAsyncSSHClient[ConnectionT: AsyncCloseable](InitSSHClient, ABC):
    """Manage the lifetime of an asynchronous SSH transport."""

    def __init__(self, host: str, port: int = 22, *options: ClientOption) -> None:
        """Configure the client without opening a connection.

        :param host: SSH server hostname.
        :param port: SSH server port.
        :param options: Client options.
        """
        self._client: ConnectionT | None = None
        self._connected = False
        super().__init__(host, port, *options)

    @property
    def client(self) -> ConnectionT | None:
        """Return the most recently created transport."""
        return self._client

    async def __aenter__(self) -> Self:
        """Return this client for scoped cleanup."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Wait for transport shutdown on context exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the transport and wait for resources to be released."""
        if self._client is not None:
            self._client.close()
            await self._client.wait_closed()
        self._connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Open an authenticated connection."""
        ...

    @abstractmethod
    async def execute(self, command: str | list[str], **options: Unpack[ExecuteOptions]) -> SSHResult:
        """Run a command and collect stdout and stderr."""
        ...

    @abstractmethod
    async def execute_live(self, command: str | list[str], **options: Unpack[LiveExecuteOptions]) -> LiveSSHResult:
        """Run a command while emitting output lines."""
        ...
