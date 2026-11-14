from __future__ import annotations

from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypedDict, TypeVar

import grpc
from google.protobuf.message import Message

from .call_options import CallOptions
from .metadata import merge_metadata
from .types import AsyncGRPCStub, ChannelOptions, GRPCStub, MetadataItems, MetadataType

# Function that configures a client when it is created.
ClientOption = Callable[["BaseGRPCClient[object]"], None]

type ClientInterceptorTypes = (
    grpc.UnaryUnaryClientInterceptor[object, object]
    | grpc.UnaryStreamClientInterceptor[object, object]
    | grpc.StreamUnaryClientInterceptor[object, object]
    | grpc.StreamStreamClientInterceptor[object, object]
)
type AsyncClientInterceptorTypes = (
    grpc.aio.UnaryUnaryClientInterceptor[object, object]
    | grpc.aio.UnaryStreamClientInterceptor[object, object]
    | grpc.aio.StreamUnaryClientInterceptor[object, object]
    | grpc.aio.StreamStreamClientInterceptor[object, object]
)

TStub = TypeVar("TStub", bound=GRPCStub)
TAsyncStub = TypeVar("TAsyncStub", bound=AsyncGRPCStub)
TRequest = TypeVar("TRequest", bound=Message)
TResponse = TypeVar("TResponse", bound=Message)

DEFAULT_TIMEOUT_SEC = 60.0


class CallArguments(TypedDict):
    """Arguments passed to grpcio methods."""

    timeout: float | None
    metadata: tuple[tuple[str, str | bytes], ...] | None
    credentials: grpc.CallCredentials | None
    wait_for_ready: bool | None
    compression: grpc.Compression | None


@dataclass(slots=True, kw_only=True)
class _ClientConfiguration:
    timeout: float | None = DEFAULT_TIMEOUT_SEC
    secure: bool = True
    ssl_credentials: grpc.ChannelCredentials | None = None
    compression: grpc.Compression | None = None
    channel_options: ChannelOptions = ()
    default_metadata: MetadataItems = ()


class BaseGRPCClient[TAnyStub](metaclass=ABCMeta):
    """Abstract base class for gRPC clients.

    Store settings shared by synchronous and asynchronous clients, apply options,
    and build effective options for each call. Sending requests and managing channels
    are implemented by subclasses.
    """

    DEFAULT_TIMEOUT_SEC = DEFAULT_TIMEOUT_SEC

    def __init__(self) -> None:
        """Create an instance with the supplied settings."""
        self._configuration = _ClientConfiguration(timeout=self.DEFAULT_TIMEOUT_SEC)
        self._interceptors: list[object] = []

    @property
    def timeout(self) -> float | None:
        """Default call timeout."""
        return self._configuration.timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self._configuration.timeout = value

    @property
    def secure(self) -> bool:
        """Whether TLS is enabled for a new channel."""
        return self._configuration.secure

    @secure.setter
    def secure(self, value: bool) -> None:
        self._configuration.secure = value

    @property
    def ssl_credentials(self) -> grpc.ChannelCredentials | None:
        """TLS credentials for a new channel."""
        return self._configuration.ssl_credentials

    @ssl_credentials.setter
    def ssl_credentials(self, value: grpc.ChannelCredentials | None) -> None:
        self._configuration.ssl_credentials = value

    @property
    def compression(self) -> grpc.Compression | None:
        """Message compression algorithm."""
        return self._configuration.compression

    @compression.setter
    def compression(self, value: grpc.Compression | None) -> None:
        self._configuration.compression = value

    @property
    def channel_options(self) -> ChannelOptions:
        """Low-level options for a new channel."""
        return self._configuration.channel_options

    @channel_options.setter
    def channel_options(self, value: ChannelOptions) -> None:
        self._configuration.channel_options = value

    @property
    def default_metadata(self) -> MetadataItems:
        """Metadata added to every request."""
        return self._configuration.default_metadata

    @default_metadata.setter
    def default_metadata(self, value: MetadataItems) -> None:
        self._configuration.default_metadata = value

    def add_interceptor(self, interceptor: object) -> None:
        """Add an interceptor before creating the channel.

        :param interceptor: synchronous or asynchronous grpcio interceptor.
        """
        self._interceptors.append(interceptor)

    @property
    @abstractmethod
    def stub_class(self) -> type[TAnyStub]:
        """Service stub class from the generated `***_pb2_grpc.py` file."""

    def _apply(self, options: Sequence[ClientOption]) -> None:
        for option in options:
            option(self)

    def _credentials(self) -> grpc.ChannelCredentials:
        return self.ssl_credentials if self.ssl_credentials is not None else grpc.ssl_channel_credentials()

    def _call_options(self, metadata: MetadataType | None, options: CallOptions | None) -> CallOptions:
        """Build effective call options from client settings and request options."""
        base = CallOptions(
            timeout=self.timeout,
            metadata=self.default_metadata,
            compression=self.compression,
        )
        request_options = options or CallOptions()
        if metadata is not None:
            request_options = CallOptions(
                timeout=request_options.timeout,
                metadata=merge_metadata(request_options.metadata, metadata),
                credentials=request_options.credentials,
                wait_for_ready=request_options.wait_for_ready,
                compression=request_options.compression,
            )
        return base.merge(request_options)

    @staticmethod
    def _call_kwargs(options: CallOptions) -> CallArguments:
        """Convert call options to grpcio arguments."""
        metadata = merge_metadata(options.metadata)
        return {
            "timeout": options.resolve_timeout(None),
            "metadata": tuple(metadata) or None,
            "credentials": options.credentials,
            "wait_for_ready": options.wait_for_ready,
            "compression": options.compression,
        }
