import os
from collections.abc import Callable
from uuid import uuid4

import grpc

from grpc_client.metadata import contains_key
from grpc_client.types import MetadataItems
from grpc_client.utils import traceparent

from .base import AsyncMetadataInterceptor, MetadataInterceptor, call_detail

DEFAULT_REQUEST_ID_KEY = "x-request-id"
DEFAULT_TRACEPARENT_KEY = "traceparent"


def default_request_id_key() -> str:
    """Get the default request identifier key name."""
    return os.getenv("GRPC_CLIENT_REQUEST_ID_KEY", DEFAULT_REQUEST_ID_KEY)


def default_traceparent_key() -> str:
    """Get the default traceparent key name."""
    return os.getenv("GRPC_CLIENT_TRACEPARENT_KEY", DEFAULT_TRACEPARENT_KEY)


class _AutogenerateMixin:
    """Shared logic for interceptors that add a generated value to metadata."""

    def __init__(self, key: str, generator: Callable[[], str]) -> None:
        """Create an instance with the supplied settings."""
        self._key = key
        self._generator = generator

    def _metadata_to_add(self, call_details: grpc.ClientCallDetails | grpc.aio.ClientCallDetails) -> MetadataItems:
        if contains_key(call_detail(call_details, "metadata", None), self._key):
            return ()
        return ((self._key, self._generator()),)


class AutogenerateRequestIdInterceptor(_AutogenerateMixin, MetadataInterceptor):
    """Interceptor that adds an identifier to every gRPC request.

    If the request already contains this key, its value is preserved.
    """

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Initialize the object.

        :param key: metadata key name, defaults to `x-request-id`
        :param generator: value generator, defaults to UUID4
        """
        super().__init__(key or default_request_id_key(), generator or _uuid4)

    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Build a request identifier if it is not already in metadata."""
        return self._metadata_to_add(call_details)


class AsyncAutogenerateRequestIdInterceptor(_AutogenerateMixin, AsyncMetadataInterceptor):
    """Asynchronous interceptor that adds an identifier to every gRPC request."""

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Initialize the object.

        :param key: metadata key name, defaults to `x-request-id`
        :param generator: value generator, defaults to UUID4
        """
        super().__init__(key or default_request_id_key(), generator or _uuid4)

    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Build a request identifier if it is not already in metadata."""
        return self._metadata_to_add(call_details)


class AutogenerateTraceparentInterceptor(_AutogenerateMixin, MetadataInterceptor):
    """Interceptor that adds traceparent to every gRPC request.

    If the request already contains traceparent, its value is preserved.
    """

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Initialize the object.

        :param key: metadata key name, defaults to `traceparent`
        :param generator: value generator, defaults to the W3C Trace Context generator
        """
        super().__init__(key or default_traceparent_key(), generator or traceparent.generate)

    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Build traceparent if it is not already in metadata."""
        return self._metadata_to_add(call_details)


class AsyncAutogenerateTraceparentInterceptor(_AutogenerateMixin, AsyncMetadataInterceptor):
    """Asynchronous interceptor that adds traceparent to every gRPC request."""

    def __init__(
        self,
        key: str | None = None,
        generator: Callable[[], str] | None = None,
    ) -> None:
        """Initialize the object.

        :param key: metadata key name, defaults to `traceparent`
        :param generator: value generator, defaults to the W3C Trace Context generator
        """
        super().__init__(key or default_traceparent_key(), generator or traceparent.generate)

    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Build traceparent if it is not already in metadata."""
        return self._metadata_to_add(call_details)


def _uuid4() -> str:
    return str(uuid4())
