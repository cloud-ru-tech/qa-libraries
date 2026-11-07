"""MCP client implementation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from copy import copy, deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Self, cast

from mcp import ClientSession, ListToolsResult, ServerCapabilities, types

from .exceptions import SessionNotInititalizedError, StreamInitFailureError
from .results import ToolCallResponse

if TYPE_CHECKING:
    from types import TracebackType

    from .custom_types import (
        AsyncDecorator,
        AsyncOperation,
        ConnectionHandlerFactory,
        MetadataProvider,
        RequestHook,
        ResponseHook,
        Streams,
    )

type ClientOption = Callable[["BaseAsyncMCPClient"], None]


def _require_streams(streams: Streams | None) -> Streams:
    if streams is None:
        raise StreamInitFailureError
    return streams


@dataclass
class MCPClientConfig:
    """Store settings applied by client options."""

    read_timeout_seconds: float | None = None
    default_metadata: dict[str, object] = field(default_factory=dict)
    metadata_providers: list[MetadataProvider] = field(default_factory=list)


class BaseAsyncMCPClient:
    """Call MCP tools through a configurable asynchronous transport."""

    def __init__(self, connection_handler: ConnectionHandlerFactory, *options: ClientOption) -> None:
        """Configure a lazily connected client.

        :param connection_handler: Factory of transport context managers.
        :param options: Built-in or custom options receiving this client.
        """
        self._config = MCPClientConfig()
        self._connection_handler = connection_handler
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._request_hooks: list[RequestHook] = []
        self._response_hooks: list[ResponseHook] = []
        self._connect_decorators: list[AsyncDecorator[None]] = []
        self._execute_decorators: list[AsyncDecorator[ToolCallResponse]] = []
        for option in options:
            option(self)

    @property
    def read_timeout_seconds(self) -> float | None:
        """Return the default read timeout."""
        return self._config.read_timeout_seconds

    @read_timeout_seconds.setter
    def read_timeout_seconds(self, value: float | None) -> None:
        """Set the default read timeout.

        :param value: Timeout in seconds, or no limit.
        """
        self._config.read_timeout_seconds = value

    def update_default_metadata(self, values: Mapping[str, object]) -> None:
        """Merge values into default request metadata.

        :param values: Metadata values to add or replace.
        """
        self._config.default_metadata.update(values)

    def add_metadata_provider(self, provider: MetadataProvider) -> None:
        """Register per-call metadata generation.

        Providers run once for each public tool, list or ping call. Explicit and
        default metadata override generated values; retry attempts reuse them.

        :param provider: Factory returning generated metadata values.
        """
        self._config.metadata_providers.append(provider)

    async def __aenter__(self) -> Self:
        """Return this client for scoped cleanup."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the connection on context exit."""
        await self.aclose()

    def add_request_hook(self, hook: RequestHook) -> None:
        """Register a request observer.

        :param hook: Callback receiving request values.
        """
        self._request_hooks.append(hook)

    def add_response_hook(self, hook: ResponseHook) -> None:
        """Register a response observer.

        :param hook: Callback receiving completed results.
        """
        self._response_hooks.append(hook)

    def add_connect_decorator(self, decorator: AsyncDecorator[None]) -> None:
        """Register a connection decorator.

        :param decorator: Wrapper for the asynchronous connection operation.
        """
        self._connect_decorators.append(decorator)

    def add_execute_decorator(self, decorator: AsyncDecorator[ToolCallResponse]) -> None:
        """Register a tool-call decorator.

        :param decorator: Wrapper for asynchronous tool execution.
        """
        self._execute_decorators.append(decorator)

    def with_options(self, *temp_options: ClientOption) -> Self:
        """Create an independent client with additional options.

        :param temp_options: Options applied after copying existing configuration.
        :return: Disconnected copy with independent configuration and hook lists.
        """
        temporary = copy(self)
        for option in temp_options:
            option(temporary)
        return temporary

    def __copy__(self) -> Self:
        """Copy settings while keeping active connections owned by the original client."""
        temporary = type(self).__new__(type(self))
        cast("dict[str, object]", temporary.__dict__).update(
            {
                **cast("dict[str, object]", self.__dict__),
                "_config": deepcopy(self._config),
                "_session": None,
                "_exit_stack": None,
                "_request_hooks": self._request_hooks.copy(),
                "_response_hooks": self._response_hooks.copy(),
                "_connect_decorators": self._connect_decorators.copy(),
                "_execute_decorators": self._execute_decorators.copy(),
            }
        )
        return temporary

    async def aclose(self) -> None:
        """Close the transport and session, including partially opened connections."""
        stack = self._exit_stack
        self._reset_connection()
        if stack is not None:
            await stack.aclose()

    async def list_tools(self, *, metadata: Mapping[str, object] | None = None) -> ListToolsResult:
        """Return the server's available tools.

        :param metadata: Per-call values overriding generated and default metadata.
        :return: Available tool descriptions.
        """
        session = await self._get_session()
        values = self._metadata(metadata)
        return await session.list_tools(
            params=types.PaginatedRequestParams(_meta=types.RequestParams.Meta.model_validate(values))
        )

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object] | None = None,
        read_timeout_seconds: float | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ToolCallResponse:
        """Execute a server tool.

        :param name: Registered tool name.
        :param arguments: Tool arguments.
        :param read_timeout_seconds: Per-call timeout overriding the client default.
        :param metadata: Values overriding default request metadata.
        :return: Result with content and protocol status.
        """
        session = await self._get_session()
        call_arguments = dict(arguments or {})
        merged_metadata = self._metadata(metadata)
        timeout = self._config.read_timeout_seconds if read_timeout_seconds is None else read_timeout_seconds
        for hook in self._request_hooks:
            hook(tool_name=name, arguments=call_arguments, metadata=merged_metadata or None)

        async def execute() -> ToolCallResponse:
            result = await session.call_tool(
                name=name,
                arguments=call_arguments,
                meta=merged_metadata or None,
                read_timeout_seconds=timedelta(seconds=timeout) if timeout is not None else None,
            )
            response = ToolCallResponse(result)
            for hook in self._response_hooks:
                hook(tool_name=name, response=response)
            return response

        operation: AsyncOperation[ToolCallResponse] = execute
        for decorator in reversed(self._execute_decorators):
            operation = decorator(operation)
        return await operation()

    async def get_server_capabilities(self) -> ServerCapabilities | None:
        """Return capabilities negotiated during initialization."""
        session = await self._get_session()
        return session.get_server_capabilities()

    async def ping_server(self, *, metadata: Mapping[str, object] | None = None) -> bool:
        """Return whether the server answers a protocol ping.

        :param metadata: Per-call values overriding generated and default metadata.
        :return: Whether the protocol ping completed successfully.
        """
        session = await self._get_session()
        request = types.ClientRequest(
            types.PingRequest(
                params=types.RequestParams(_meta=types.RequestParams.Meta.model_validate(self._metadata(metadata))),
            )
        )
        response = await session.send_request(request, cast("type[types.Result]", types.EmptyResult))
        return bool(response)

    def _metadata(self, explicit: Mapping[str, object] | None) -> dict[str, object]:
        values: dict[str, object] = {}
        for provider in self._config.metadata_providers:
            values.update(provider())
        return {**values, **self._config.default_metadata, **(explicit or {})}

    def _reset_connection(self) -> None:
        self._session = None
        self._exit_stack = None

    async def _get_session(self) -> ClientSession:
        if self._session is None:
            operation: AsyncOperation[None] = self._connect
            for decorator in reversed(self._connect_decorators):
                operation = decorator(operation)
            await operation()
        if self._session is None:
            raise SessionNotInititalizedError
        return self._session

    async def _connect(self) -> None:
        self._exit_stack = AsyncExitStack()
        try:
            streams = await cast(
                "Awaitable[Streams | None]", self._exit_stack.enter_async_context(self._connection_handler())
            )
            read_stream, write_stream = _require_streams(streams)
            self._session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await self._session.initialize()
        except BaseException:
            await self.aclose()
            raise
