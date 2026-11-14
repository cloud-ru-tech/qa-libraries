from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Self

DEFAULT_EXPIRY_LEEWAY = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class Token:
    """Access token with an expiration time."""

    access_token: str
    expires_at: datetime

    @classmethod
    def with_lifetime(cls, access_token: str, expires_in: int) -> Self:
        """Create a token from its lifetime in seconds.

        Subtract a safety margin so the token does not expire between sending and processing the request.
        Limit the margin to half the lifetime for short-lived tokens so they do not expire immediately.

        :param access_token: Access token value
        :param expires_in: Token lifetime in seconds reported by IAM
        :return: Token with a calculated expiration time
        """
        lifetime = timedelta(seconds=expires_in)
        leeway = min(DEFAULT_EXPIRY_LEEWAY, lifetime / 2)
        return cls(access_token, datetime.now(UTC) + lifetime - leeway)

    @property
    def is_expired(self) -> bool:
        """Check whether the token has expired."""
        return datetime.now(UTC) >= self.expires_at


class AuthStore(ABC):
    """Synchronous token store interface."""

    @abstractmethod
    def get(self, key: str) -> Token | None:
        """Get a token by key."""

    @abstractmethod
    def set(self, key: str, token: Token) -> None:
        """Store a token by key."""


class AsyncAuthStore(ABC):
    """Asynchronous token store interface.

    Use a separate interface to avoid blocking the event loop when accessing external storage.
    """

    @abstractmethod
    async def get(self, key: str) -> Token | None:
        """Get a token by key."""

    @abstractmethod
    async def set(self, key: str, token: Token) -> None:
        """Store a token by key."""


class InMemoryAuthStore(AuthStore):
    """Synchronous in-memory token store."""

    def __init__(self) -> None:
        """Initialize the object."""
        self._tokens: dict[str, Token] = {}

    def get(self, key: str) -> Token | None:
        """Get a stored token.

        :param key: Authentication key ID.
        :return: Token, or None if the key is not found.
        """
        return self._tokens.get(key)

    def set(self, key: str, token: Token) -> None:
        """Store an authentication token.

        :param key: Authentication key ID.
        :param token: Token to store.
        """
        self._tokens[key] = token


class InMemoryAsyncAuthStore(AsyncAuthStore):
    """Asynchronous in-memory token store."""

    def __init__(self) -> None:
        """Initialize the object."""
        self._tokens: dict[str, Token] = {}

    async def get(self, key: str) -> Token | None:
        """Get a stored token.

        :param key: Authentication key ID.
        :return: Token, or None if the key is not found.
        """
        return self._tokens.get(key)

    async def set(self, key: str, token: Token) -> None:
        """Store an authentication token.

        :param key: Authentication key ID.
        :param token: Token to store.
        """
        self._tokens[key] = token
