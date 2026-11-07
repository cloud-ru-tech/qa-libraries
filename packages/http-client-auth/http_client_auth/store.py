from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Self

DEFAULT_EXPIRY_LEEWAY = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class Token:
    """Токен доступа со временем истечения."""

    access_token: str
    expires_at: datetime

    @classmethod
    def with_lifetime(cls, access_token: str, expires_in: int) -> Self:
        """Создать токен, зная его время жизни в секундах.

        Из срока вычитается запас, чтобы токен не протух в пути между отправкой и обработкой запроса.
        Для короткоживущих токенов запас урезается до половины срока, иначе токен был бы просрочен сразу.

        :param access_token: значение токена доступа
        :param expires_in: время жизни токена в секундах по данным IAM
        :return: токен с вычисленным временем истечения
        """
        lifetime = timedelta(seconds=expires_in)
        leeway = min(DEFAULT_EXPIRY_LEEWAY, lifetime / 2)
        return cls(access_token, datetime.now(UTC) + lifetime - leeway)

    @property
    def is_expired(self) -> bool:
        """Истек ли токен."""
        return datetime.now(UTC) >= self.expires_at


class AuthStore(ABC):
    """Интерфейс синхронного хранилища токенов."""

    @abstractmethod
    def get(self, key: str) -> Token | None:
        """Получить токен по ключу."""

    @abstractmethod
    def set(self, key: str, token: Token) -> None:
        """Сохранить токен по ключу."""


class AsyncAuthStore(ABC):
    """Интерфейс асинхронного хранилища токенов.

    Отдельный интерфейс нужен, чтобы обращение к внешнему хранилищу не блокировало event loop.
    """

    @abstractmethod
    async def get(self, key: str) -> Token | None:
        """Получить токен по ключу."""

    @abstractmethod
    async def set(self, key: str, token: Token) -> None:
        """Сохранить токен по ключу."""


class InMemoryAuthStore(AuthStore):
    """Синхронное хранилище токенов в памяти."""

    def __init__(self) -> None:
        """Инициализировать объект."""
        self._tokens: dict[str, Token] = {}

    def get(self, key: str) -> Token | None:
        """Получить сохранённый токен.

        :param key: идентификатор ключа авторизации.
        :return: токен или None, если ключ не найден.
        """
        return self._tokens.get(key)

    def set(self, key: str, token: Token) -> None:
        """Сохранить токен авторизации.

        :param key: идентификатор ключа авторизации.
        :param token: сохраняемый токен.
        """
        self._tokens[key] = token


class InMemoryAsyncAuthStore(AsyncAuthStore):
    """Асинхронное хранилище токенов в памяти."""

    def __init__(self) -> None:
        """Инициализировать объект."""
        self._tokens: dict[str, Token] = {}

    async def get(self, key: str) -> Token | None:
        """Получить сохранённый токен.

        :param key: идентификатор ключа авторизации.
        :return: токен или None, если ключ не найден.
        """
        return self._tokens.get(key)

    async def set(self, key: str, token: Token) -> None:
        """Сохранить токен авторизации.

        :param key: идентификатор ключа авторизации.
        :param token: сохраняемый токен.
        """
        self._tokens[key] = token
