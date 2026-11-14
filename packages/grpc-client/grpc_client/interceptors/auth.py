from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, cast, override

import grpc

from grpc_client.metadata import contains_key

from .base import (
    AsyncMetadataInterceptor,
    AsyncUnaryContinuation,
    ContinuationType,
    MetadataInterceptor,
    aio_call_details,
    call_detail,
    continue_async,
    outcome_code,
    with_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from grpc_client.types import AsyncClientAuth, ClientAuth, MetadataItems

DEFAULT_AUTH_KEY = "authorization"
DEFAULT_AUTH_SCHEME = "Bearer"


class AuthInterceptor(MetadataInterceptor):
    """Interceptor that adds an access token to request metadata.

    Request a token from the supplied `ClientAuth` implementation. If the service returns `UNAUTHENTICATED`,
    the interceptor requests a new token to replace the rejected one and retries the unary request.

    Only unary requests are retried: a request stream is exhausted after its first send,
    and response stream final status is known only after reading, so
    such calls cannot be retried transparently.

    If the caller supplies a custom authorization header, the interceptor does not interfere:
    no token is requested and no retry is performed.
    """

    def __init__(
        self,
        auth: ClientAuth,
        key: str = DEFAULT_AUTH_KEY,
        scheme: str = DEFAULT_AUTH_SCHEME,
        *,
        retry_on_unauthenticated: bool = True,
    ) -> None:
        """Initialize the object.

        :param auth: access token provider
        :param key: metadata key name, defaults to `authorization`
        :param scheme: authorization scheme, defaults to `Bearer`
        :param retry_on_unauthenticated: whether to retry a unary request with a new token after UNAUTHENTICATED
        """
        self._auth = auth
        self._key = key
        self._scheme = scheme
        self._retry_on_unauthenticated = retry_on_unauthenticated

    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Build an authorization header unless the caller supplied one."""
        if self._has_own_auth(call_details):
            return ()
        return self._auth_metadata(self._auth.token())

    @override
    def intercept_unary_unary(
        self,
        continuation: ContinuationType,
        client_call_details: grpc.ClientCallDetails,
        request: object,
    ) -> grpc.CallFuture[object]:
        if self._has_own_auth(client_call_details):
            return cast("grpc.CallFuture[object]", continuation(client_call_details, request))

        # Remember the token before sending: authentication can then distinguish
        # a genuinely expired token from one already refreshed by another request.
        token = self._auth.token()
        outcome = continuation(with_metadata(client_call_details, self._auth_metadata(token)), request)

        if not self._should_retry(outcome):
            return cast("grpc.CallFuture[object]", outcome)

        refreshed = self._auth.refresh(token)
        return cast(
            "grpc.CallFuture[object]",
            continuation(with_metadata(client_call_details, self._auth_metadata(refreshed)), request),
        )

    def _auth_metadata(self, token: str) -> MetadataItems:
        return ((self._key, f"{self._scheme} {token}"),)

    def _should_retry(self, outcome: object) -> bool:
        if not self._retry_on_unauthenticated:
            return False
        return outcome_code(outcome) is grpc.StatusCode.UNAUTHENTICATED

    def _has_own_auth(self, call_details: grpc.ClientCallDetails) -> bool:
        return contains_key(call_detail(call_details, "metadata", None), self._key)


class AsyncAuthInterceptor(AsyncMetadataInterceptor):
    """Asynchronous interceptor that adds an access token to request metadata.

    Request a token from the supplied `AsyncClientAuth` implementation. If the service returns
    `UNAUTHENTICATED`, the interceptor requests a new token to replace the rejected one and sends
    the unary request again.

    Only unary requests are retried: a request stream is exhausted after its first send,
    and response stream final status is known only after reading, so
    such calls cannot be retried transparently.

    If the caller supplies a custom authorization header, the interceptor does not interfere:
    no token is requested and no retry is performed.
    """

    def __init__(
        self,
        auth: AsyncClientAuth,
        key: str = DEFAULT_AUTH_KEY,
        scheme: str = DEFAULT_AUTH_SCHEME,
        *,
        retry_on_unauthenticated: bool = True,
    ) -> None:
        """Initialize the object.

        :param auth: access token provider
        :param key: metadata key name, defaults to `authorization`
        :param scheme: authorization scheme, defaults to `Bearer`
        :param retry_on_unauthenticated: whether to retry a unary request with a new token after UNAUTHENTICATED
        """
        self._auth = auth
        self._key = key
        self._scheme = scheme
        self._retry_on_unauthenticated = retry_on_unauthenticated

    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Build an authorization header unless the caller supplied one."""
        if self._has_own_auth(call_details):
            return ()
        return self._auth_metadata(await self._auth.token())

    @override
    async def intercept_unary_unary(
        self,
        continuation: AsyncUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
        if self._has_own_auth(client_call_details):
            return await continue_async(continuation, client_call_details, request)

        token = await self._auth.token()
        call: object = await continue_async(
            continuation, aio_call_details(client_call_details, self._auth_metadata(token)), request
        )

        if not await self._should_retry(call):
            return call

        refreshed = await self._auth.refresh(token)
        return await continue_async(
            continuation, aio_call_details(client_call_details, self._auth_metadata(refreshed)), request
        )

    def _auth_metadata(self, token: str) -> MetadataItems:
        return ((self._key, f"{self._scheme} {token}"),)

    async def _should_retry(self, call: object) -> bool:
        if not self._retry_on_unauthenticated:
            return False

        code = cast("Callable[[], Awaitable[grpc.StatusCode] | grpc.StatusCode] | None", getattr(call, "code", None))
        if not callable(code):
            return False

        try:
            result = code()
            status = await result if inspect.isawaitable(result) else result
        except grpc.aio.AioRpcError as error:
            status = error.code()

        return status is grpc.StatusCode.UNAUTHENTICATED

    def _has_own_auth(self, call_details: grpc.aio.ClientCallDetails) -> bool:
        return contains_key(call_detail(call_details, "metadata", None), self._key)


__all__ = ["AsyncAuthInterceptor", "AuthInterceptor"]
