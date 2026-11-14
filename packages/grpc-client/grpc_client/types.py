from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

import grpc

# gRPC metadata value.
#
# Binary values are allowed only for keys ending in `-bin`; all others must be strings.
MetadataValue = str | bytes

# Metadata as a sequence of pairs that supports repeated keys.
MetadataItems = Sequence[tuple[str, MetadataValue]]

# Request metadata: a dictionary or sequence of pairs.
MetadataType = Mapping[str, MetadataValue] | MetadataItems

# Low-level grpcio channel options.
ChannelOptions = Sequence[tuple[str, object]]


@runtime_checkable
class GRPCStub(Protocol):
    """Generated service stub using a synchronous channel."""

    def __init__(self, channel: grpc.Channel) -> None:
        """Create a stub over a synchronous channel."""


@runtime_checkable
class AsyncGRPCStub(Protocol):
    """Generated service stub using an asynchronous channel."""

    def __init__(self, channel: grpc.aio.Channel) -> None:
        """Create a stub over an asynchronous channel."""


class ClientAuth(Protocol):
    """Access token provider for the synchronous client.

    The protocol has no `runtime_checkable`: `isinstance()` only checks method presence
    and does not distinguish synchronous and asynchronous implementations, making this check
    misleading. The client distinguishes them by whether `token()` is a coroutine.

    Implementations only supply tokens: caching, expiry, and external service calls are
    their responsibility. The client adds tokens to metadata and retries after `UNAUTHENTICATED`.
    """

    def token(self) -> str:
        """Get a valid access token."""
        ...

    def refresh(self, rejected_token: str) -> str:
        """Issue a new token to replace the one rejected by the service.

        The rejected token lets implementations distinguish an actually expired token
        from one already refreshed by another caller while waiting, avoiding unnecessary external calls.

        :param rejected_token: token rejected by the service with UNAUTHENTICATED
        :return: valid access token
        """
        ...


class AsyncClientAuth(Protocol):
    """Access token provider for the asynchronous client."""

    async def token(self) -> str:
        """Get a valid access token."""
        ...

    async def refresh(self, rejected_token: str) -> str:
        """Issue a new token to replace the one rejected by the service.

        :param rejected_token: token rejected by the service with UNAUTHENTICATED
        :return: valid access token
        """
        ...
