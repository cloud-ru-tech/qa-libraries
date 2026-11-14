import asyncio
import threading
import weakref
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import MutableMapping

from http_client_auth import (
    AsyncAuthStore,
    AuthData,
    AuthStore,
    InMemoryAsyncAuthStore,
    InMemoryAuthStore,
    Token,
)


class IamClient(Protocol):
    """IAM authentication provider.

    Defined as a protocol rather than concrete classes to support a public API client,
    an OpenID client, or a custom implementation reading credentials from storage.

    The protocol is for static checking only: `isinstance()` cannot distinguish
    synchronous and asynchronous implementations, so `runtime_checkable` is not used here.
    """

    def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Get authentication data using a key and secret."""
        ...


class AsyncIamClient(Protocol):
    """Asynchronous IAM authentication provider."""

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Get authentication data using a key and secret."""
        ...


class IamGrpcAuth:
    """IAM access token provider for the synchronous gRPC client.

    Implements `grpc_client.ClientAuth`: provides a valid token and issues a new one
    when the service rejects the previous one. The client adds headers and retries requests.

    Store the token in `AuthStore` with its IAM-provided lifetime and reissue it
    on expiry. IAM calls are protected by a lock, so concurrent requests
    do not trigger multiple token requests.

    The lock belongs to the instance. The guarantee of one IAM request per refresh applies
    within one authentication object: two objects sharing storage may issue
    different tokens simultaneously. Create one object per credential set and reuse it.
    """

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        iam_client: IamClient,
        store: AuthStore | None = None,
    ) -> None:
        """Initialize the object.

        :param key_id: key identifier
        :param key_secret: secret key
        :param iam_client: IAM service client
        :param store: token storage, defaults to in-memory storage
        """
        self._key_id = key_id
        self._key_secret = key_secret
        self._iam_client = iam_client

        # Compare with None rather than truthiness: an empty storage may have __bool__ == False.
        self._store = store if store is not None else InMemoryAuthStore()
        self._lock = threading.Lock()
        self._generation = 0

    def token(self) -> str:
        """Get a valid access token.

        :return: access token
        """
        with self._lock:
            token = self._store.get(self._key_id)
            if token is None or token.is_expired:
                token = self._issue_token()
            return token.access_token

    def refresh(self, rejected_token: str) -> str:
        """Issue a new token to replace the one rejected by the service.

        If another request on this object refreshed the token while the current request awaited
        the lock, no IAM request is needed. Detect refreshes using a counter,
        rather than token text: IAM may return the same value, so string comparison
        would send every waiting caller to IAM.

        Account for refreshes since entering this method. A refresh
        completed earlier is detected by token text if IAM returned a new value.

        :param rejected_token: token rejected by the service with UNAUTHENTICATED
        :return: access token
        """
        seen_generation = self._generation

        with self._lock:
            stored = self._store.get(self._key_id)
            refreshed_by_neighbour = self._generation != seen_generation

            if (
                stored is not None
                and not stored.is_expired
                and (refreshed_by_neighbour or stored.access_token != rejected_token)
            ):
                return stored.access_token

            return self._issue_token().access_token

    def _issue_token(self) -> Token:
        auth_data = self._iam_client.authorize(self._key_id, self._key_secret)
        token = Token.with_lifetime(auth_data.access_token, auth_data.expires_in)
        self._store.set(self._key_id, token)
        # The generation increases on every issue, including expired token refresh in token():
        # otherwise a request whose token was rejected would miss a refresh that already happened.
        self._generation += 1
        return token


class IamGrpcAsyncAuth:
    """IAM access token provider for the asynchronous gRPC client.

    Implements `grpc_client.AsyncClientAuth` and behaves like `IAM_GrpcAuth`,
    including the restriction that a single IAM request is guaranteed within
    a single authentication object.

    The object supports multiple event loops: each loop has its own lock,
    so a client in another thread does not hang. IAM request deduplication
    applies within each loop; tokens issued in one are visible to others in shared storage.
    """

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        iam_client: AsyncIamClient,
        store: AsyncAuthStore | None = None,
    ) -> None:
        """Initialize the object.

        :param key_id: key identifier
        :param key_secret: secret key
        :param iam_client: asynchronous IAM service client
        :param store: token storage, defaults to in-memory storage
        """
        self._key_id = key_id
        self._key_secret = key_secret
        self._iam_client = iam_client

        # Compare with None rather than truthiness: an empty storage may have __bool__ == False.
        self._store = store if store is not None else InMemoryAsyncAuthStore()
        # asyncio.Lock is bound to its event loop: sharing one lock would cause
        # a client in another thread to wait for a wakeup that will never happen.
        self._locks: MutableMapping[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()
        self._locks_guard = threading.Lock()
        self._generation = 0

    @property
    def _lock(self) -> asyncio.Lock:
        """Lock for the current event loop."""
        loop = asyncio.get_running_loop()

        with self._locks_guard:
            lock = self._locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[loop] = lock
            return lock

    async def token(self) -> str:
        """Get a valid access token.

        :return: access token
        """
        async with self._lock:
            token = await self._store.get(self._key_id)
            if token is None or token.is_expired:
                token = await self._issue_token()
            return token.access_token

    async def refresh(self, rejected_token: str) -> str:
        """Issue a new token to replace the one rejected by the service.

        If another coroutine on this object refreshed the token while the current coroutine awaited
        the lock, no IAM request is needed. Detect refreshes using a counter,
        rather than token text: IAM may return the same value.

        :param rejected_token: token rejected by the service with UNAUTHENTICATED
        :return: access token
        """
        seen_generation = self._generation

        async with self._lock:
            stored = await self._store.get(self._key_id)
            refreshed_by_neighbour = self._generation != seen_generation

            if (
                stored is not None
                and not stored.is_expired
                and (refreshed_by_neighbour or stored.access_token != rejected_token)
            ):
                return stored.access_token

            return (await self._issue_token()).access_token

    async def _issue_token(self) -> Token:
        auth_data = await self._iam_client.authorize(self._key_id, self._key_secret)
        token = Token.with_lifetime(auth_data.access_token, auth_data.expires_in)
        await self._store.set(self._key_id, token)
        # The generation increases on every issue, including expired token refresh in token().
        self._generation += 1
        return token


IAM_GrpcAuth = IamGrpcAuth
IAM_GrpcAsyncAuth = IamGrpcAsyncAuth
