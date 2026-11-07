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
    """Источник данных авторизации IAM.

    Описан протоколом, а не конкретными классами: так подойдет и клиент публичного API,
    и клиент OpenID, и собственная реализация — например, читающая учетные данные из хранилища.

    Протокол предназначен только для статической проверки: `isinstance()` не отличил бы
    синхронную реализацию от асинхронной, поэтому `runtime_checkable` здесь не используется.
    """

    def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Получить данные авторизации по ключу и секрету."""
        ...


class AsyncIamClient(Protocol):
    """Асинхронный источник данных авторизации IAM."""

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Получить данные авторизации по ключу и секрету."""
        ...


class IamGrpcAuth:
    """Источник токенов доступа IAM для синхронного gRPC-клиента.

    Реализует контракт `grpc_client.ClientAuth`: выдает действующий токен и выпускает новый,
    когда сервис отверг предыдущий. Подстановкой заголовка и повтором запроса занимается сам клиент.

    Токен хранится в `AuthStore` вместе со сроком жизни, полученным от IAM, и перевыпускается
    при истечении. Обращения к IAM защищены блокировкой, поэтому параллельные запросы
    не приводят к нескольким походам за токеном.

    Блокировка принадлежит экземпляру. Гарантия «один поход в IAM на обновление» действует
    в пределах одного объекта авторизации: два объекта с общим хранилищем могут выпустить
    разные токены одновременно. Создавайте один объект на набор учетных данных и переиспользуйте его.
    """

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        iam_client: IamClient,
        store: AuthStore | None = None,
    ) -> None:
        """Инициализатор.

        :param key_id: идентификатор ключа
        :param key_secret: секретный ключ
        :param iam_client: клиент сервиса IAM
        :param store: хранилище токенов, по умолчанию хранилище в памяти
        """
        self._key_id = key_id
        self._key_secret = key_secret
        self._iam_client = iam_client

        # Сравнение с None, а не проверка на истинность: у пустого хранилища может быть __bool__ == False.
        self._store = store if store is not None else InMemoryAuthStore()
        self._lock = threading.Lock()
        self._generation = 0

    def token(self) -> str:
        """Получить действующий токен доступа.

        :return: токен доступа
        """
        with self._lock:
            token = self._store.get(self._key_id)
            if token is None or token.is_expired:
                token = self._issue_token()
            return token.access_token

    def refresh(self, rejected_token: str) -> str:
        """Выпустить новый токен взамен отвергнутого сервисом.

        Если токен успел обновить соседний запрос этого же объекта, пока текущий ждал
        блокировку, обращаться в IAM не нужно. Факт обновления определяется по счетчику,
        а не по тексту токена: IAM вправе вернуть прежнее значение, и тогда сравнение строк
        отправило бы в IAM каждого ожидающего.

        Учитываются обновления, случившиеся с момента входа в этот метод. Обновление,
        завершившееся раньше, распознается по тексту токена — если IAM вернул новое значение.

        :param rejected_token: токен, который сервис отверг с ошибкой UNAUTHENTICATED
        :return: токен доступа
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
        # Поколение растет при любом выпуске, включая обновление истекшего токена в token():
        # иначе запрос, чей токен отвергли, не увидел бы уже случившееся обновление.
        self._generation += 1
        return token


class IamGrpcAsyncAuth:
    """Источник токенов доступа IAM для асинхронного gRPC-клиента.

    Реализует контракт `grpc_client.AsyncClientAuth` и ведет себя так же, как `IAM_GrpcAuth`,
    включая ограничение: гарантия единственного обращения в IAM действует в пределах
    одного объекта авторизации.

    Объект можно использовать из нескольких циклов событий: блокировка своя у каждого цикла,
    поэтому клиент из другого потока не зависает. Дедупликация обращений в IAM при этом
    работает внутри цикла — токен, выпущенный в одном, остальные увидят в общем хранилище.
    """

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        iam_client: AsyncIamClient,
        store: AsyncAuthStore | None = None,
    ) -> None:
        """Инициализатор.

        :param key_id: идентификатор ключа
        :param key_secret: секретный ключ
        :param iam_client: асинхронный клиент сервиса IAM
        :param store: хранилище токенов, по умолчанию хранилище в памяти
        """
        self._key_id = key_id
        self._key_secret = key_secret
        self._iam_client = iam_client

        # Сравнение с None, а не проверка на истинность: у пустого хранилища может быть __bool__ == False.
        self._store = store if store is not None else InMemoryAsyncAuthStore()
        # asyncio.Lock привязан к своему циклу событий: общий объект блокировки заставил бы
        # клиент из другого потока ждать пробуждения, которого не будет.
        self._locks: MutableMapping[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()
        self._locks_guard = threading.Lock()
        self._generation = 0

    @property
    def _lock(self) -> asyncio.Lock:
        """Блокировка текущего цикла событий."""
        loop = asyncio.get_running_loop()

        with self._locks_guard:
            lock = self._locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[loop] = lock
            return lock

    async def token(self) -> str:
        """Получить действующий токен доступа.

        :return: токен доступа
        """
        async with self._lock:
            token = await self._store.get(self._key_id)
            if token is None or token.is_expired:
                token = await self._issue_token()
            return token.access_token

    async def refresh(self, rejected_token: str) -> str:
        """Выпустить новый токен взамен отвергнутого сервисом.

        Если токен успела обновить соседняя корутина этого же объекта, пока текущая ждала
        блокировку, обращаться в IAM не нужно. Факт обновления определяется по счетчику,
        а не по тексту токена: IAM вправе вернуть прежнее значение.

        :param rejected_token: токен, который сервис отверг с ошибкой UNAUTHENTICATED
        :return: токен доступа
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
        # Поколение растет при любом выпуске, включая обновление истекшего токена в token().
        self._generation += 1
        return token


IAM_GrpcAuth = IamGrpcAuth
IAM_GrpcAsyncAuth = IamGrpcAsyncAuth
