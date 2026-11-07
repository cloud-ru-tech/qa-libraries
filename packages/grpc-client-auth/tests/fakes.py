import asyncio
import threading
import time
from itertools import count
from uuid import uuid4

from http_client_auth import AuthData


class SlowIamClient:
    """Синхронный клиент IAM, отвечающий с задержкой.

    Задержка нужна тестам конкуренции: без нее поток успевает выпустить и сохранить токен
    раньше, чем соседний войдет в обновление, и тест проходил бы даже без блокировки.
    """

    def __init__(self, delay: float = 0.05, prefix: str = "token") -> None:
        """Создать экземпляр с переданными настройками."""
        self._delay = delay
        self._prefix = prefix
        self._counter = count(1)
        self._lock = threading.Lock()
        self.calls = 0

    def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 — сигнатура задана контрактом
        """Выдать очередной токен, задержавшись на заданное время."""
        with self._lock:
            self.calls += 1
            number = next(self._counter)

        time.sleep(self._delay)
        return AuthData(access_token=f"{self._prefix}-{number}", expires_in=3600)


class ConstantIamClient:
    """Синхронный клиент IAM, всегда возвращающий один и тот же токен.

    IAM вправе вернуть прежнее значение: тогда обновление нельзя распознать по тексту токена.
    """

    def __init__(self, delay: float = 0.05, token: str | None = None) -> None:
        """Создать экземпляр с переданными настройками."""
        self._delay = delay
        self._token = token if token is not None else uuid4().hex
        self._lock = threading.Lock()
        self.calls = 0

    def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 — сигнатура задана контрактом
        """Выдать неизменный токен, задержавшись на заданное время."""
        with self._lock:
            self.calls += 1

        time.sleep(self._delay)
        return AuthData(access_token=self._token, expires_in=3600)


class ConstantAsyncIamClient:
    """Асинхронный клиент IAM, всегда возвращающий один и тот же токен."""

    def __init__(self, delay: float = 0.05, token: str | None = None) -> None:
        """Создать экземпляр с переданными настройками."""
        self._delay = delay
        self._token = token if token is not None else uuid4().hex
        self.calls = 0

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 — сигнатура задана контрактом
        """Выдать неизменный токен, задержавшись на заданное время."""
        self.calls += 1
        await asyncio.sleep(self._delay)
        return AuthData(access_token=self._token, expires_in=3600)


class SlowAsyncIamClient:
    """Асинхронный клиент IAM, отвечающий с задержкой."""

    def __init__(self, delay: float = 0.05, prefix: str = "async-token") -> None:
        """Создать экземпляр с переданными настройками."""
        self._delay = delay
        self._prefix = prefix
        self._counter = count(1)
        self.calls = 0

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:  # noqa: ARG002 — сигнатура задана контрактом
        """Выдать очередной токен, задержавшись на заданное время."""
        self.calls += 1
        number = next(self._counter)

        await asyncio.sleep(self._delay)
        return AuthData(access_token=f"{self._prefix}-{number}", expires_in=3600)
