import asyncio
import threading
import time
from itertools import count
from uuid import uuid4

from http_client_auth import AuthData


class SlowIamClient:
    """Synchronous IAM client that responds after a delay.

    The delay is needed for concurrency tests: without it, a thread can issue and save the token
    before another starts refreshing, so the test would pass even without a lock.
    """

    def __init__(self, delay: float = 0.05, prefix: str = "token") -> None:
        """Create an instance with the supplied settings."""
        self._delay = delay
        self._prefix = prefix
        self._counter = count(1)
        self._lock = threading.Lock()
        self.calls = 0

    def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 - the contract defines the signature
        """Return the next token after the specified delay."""
        with self._lock:
            self.calls += 1
            number = next(self._counter)

        time.sleep(self._delay)
        return AuthData(access_token=f"{self._prefix}-{number}", expires_in=3600)


class ConstantIamClient:
    """Synchronous IAM client that always returns the same token.

    IAM may return the same value, so refreshes cannot be identified by token text.
    """

    def __init__(self, delay: float = 0.05, token: str | None = None) -> None:
        """Create an instance with the supplied settings."""
        self._delay = delay
        self._token = token if token is not None else uuid4().hex
        self._lock = threading.Lock()
        self.calls = 0

    def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 - the contract defines the signature
        """Return a fixed token after the specified delay."""
        with self._lock:
            self.calls += 1

        time.sleep(self._delay)
        return AuthData(access_token=self._token, expires_in=3600)


class ConstantAsyncIamClient:
    """Asynchronous IAM client that always returns the same token."""

    def __init__(self, delay: float = 0.05, token: str | None = None) -> None:
        """Create an instance with the supplied settings."""
        self._delay = delay
        self._token = token if token is not None else uuid4().hex
        self.calls = 0

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 - the contract defines the signature
        """Return a fixed token after the specified delay."""
        self.calls += 1
        await asyncio.sleep(self._delay)
        return AuthData(access_token=self._token, expires_in=3600)


class SlowAsyncIamClient:
    """Asynchronous IAM client that responds after a delay."""

    def __init__(self, delay: float = 0.05, prefix: str = "async-token") -> None:
        """Create an instance with the supplied settings."""
        self._delay = delay
        self._prefix = prefix
        self._counter = count(1)
        self.calls = 0

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 - the contract defines the signature
        """Return the next token after the specified delay."""
        self.calls += 1
        number = next(self._counter)

        await asyncio.sleep(self._delay)
        return AuthData(access_token=f"{self._prefix}-{number}", expires_in=3600)
