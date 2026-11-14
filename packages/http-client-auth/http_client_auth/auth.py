import asyncio
import threading
from collections.abc import AsyncGenerator, Generator

import httpx

from .iam_client import IAM_AsyncClientT, IAM_SyncClientT
from .store import AsyncAuthStore, AuthStore, InMemoryAsyncAuthStore, InMemoryAuthStore, Token


class IamAuth(httpx.Auth):
    """Obtain a token from IAM and add it to HTTP requests."""

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        iam_client: IAM_SyncClientT,
        store: AuthStore | None = None,
    ) -> None:
        """Initialize the object.

        :param key_id: Value of ``key_id``.
        :param key_secret: Value of ``key_secret``.
        :param iam_client: Value of ``iam_client``.
        :param store: Value of ``store``.
        """
        self._key_id = key_id
        self._key_secret = key_secret
        self._iam_client = iam_client

        # Compare with None rather than checking truthiness: an empty store may have __bool__ == False.
        self._store = store if store is not None else InMemoryAuthStore()
        self._lock = threading.Lock()

    def sync_auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        """Add an access token to the request and retry with a new token if the service rejects it.

        :param request: Outgoing request
        :return: Generator yielding a request with an Authorization header
        """
        # A streaming body is exhausted on the first send, while a 401 causes the request to be resent.
        request.read()

        token = self._get_token()
        request.headers["Authorization"] = f"Bearer {token.access_token}"
        response = yield request

        if response.status_code == httpx.codes.UNAUTHORIZED:
            token = self._refresh_token(token)
            request.headers["Authorization"] = f"Bearer {token.access_token}"
            yield request

    def _get_token(self) -> Token:
        with self._lock:
            token = self._store.get(self._key_id)
            if token is None or token.is_expired:
                token = self._issue_token()
            return token

    def _refresh_token(self, rejected: Token) -> Token:
        # Avoid another IAM call if a different thread has already refreshed the token.
        with self._lock:
            token = self._store.get(self._key_id)
            if token is None or token.is_expired or token == rejected:
                token = self._issue_token()
            return token

    def _issue_token(self) -> Token:
        auth_data = self._iam_client.authorize(self._key_id, self._key_secret)
        token = Token.with_lifetime(auth_data.access_token, auth_data.expires_in)
        self._store.set(self._key_id, token)
        return token


class IamAsyncAuth(httpx.Auth):
    """Obtain a token from IAM asynchronously and add it to HTTP requests."""

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        iam_client: IAM_AsyncClientT,
        store: AsyncAuthStore | None = None,
    ) -> None:
        """Initialize the object.

        :param key_id: Value of ``key_id``.
        :param key_secret: Value of ``key_secret``.
        :param iam_client: Value of ``iam_client``.
        :param store: Value of ``store``.
        """
        self._key_id = key_id
        self._key_secret = key_secret
        self._iam_client = iam_client

        # Compare with None rather than checking truthiness: an empty store may have __bool__ == False.
        self._store = store if store is not None else InMemoryAsyncAuthStore()
        self._lock = asyncio.Lock()

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Add an access token to the request and retry with a new token if the service rejects it.

        :param request: Outgoing request
        :return: Generator yielding a request with an Authorization header
        """
        # A streaming body is exhausted on the first send, while a 401 causes the request to be resent.
        await request.aread()

        token = await self._get_token()
        request.headers["Authorization"] = f"Bearer {token.access_token}"
        response = yield request

        if response.status_code == httpx.codes.UNAUTHORIZED:
            token = await self._refresh_token(token)
            request.headers["Authorization"] = f"Bearer {token.access_token}"
            yield request

    async def _get_token(self) -> Token:
        async with self._lock:
            token = await self._store.get(self._key_id)
            if token is None or token.is_expired:
                token = await self._issue_token()
            return token

    async def _refresh_token(self, rejected: Token) -> Token:
        # Avoid another IAM call if a concurrent coroutine has already refreshed the token.
        async with self._lock:
            token = await self._store.get(self._key_id)
            if token is None or token.is_expired or token == rejected:
                token = await self._issue_token()
            return token

    async def _issue_token(self) -> Token:
        auth_data = await self._iam_client.authorize(self._key_id, self._key_secret)
        token = Token.with_lifetime(auth_data.access_token, auth_data.expires_in)
        await self._store.set(self._key_id, token)
        return token


IAM_Auth = IamAuth
IAM_AsyncAuth = IamAsyncAuth
