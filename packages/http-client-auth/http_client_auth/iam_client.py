from dataclasses import dataclass
from typing import Self, cast

import httpx
from http_client import AsyncHttpClient, HttpClient
from httpx import codes

from .exceptions import IAM_AuthError, IAM_InvalidJsonResponseError

PUBLIC_API_AUTHORIZE_ROUTE = "/api/v1/auth/token"
OPEN_ID_AUTHORIZE_ROUTE = "/auth/system/openid/token"

# Эти поля IAM не входят в маскирование http-client по умолчанию.
IAM_SANITIZE_KEYS = ("client_secret", "id_token")


@dataclass(frozen=True, slots=True)
class AuthData:
    """Данные авторизации, полученные от сервиса IAM."""

    access_token: str
    expires_in: int
    id_token: str | None = None

    def __post_init__(self) -> None:
        """Проверить типы полей ответа IAM.

        :raises TypeError: если поля ответа имеют неверный тип.
        """
        _validate_value_type(self.access_token, str, "access_token")
        _validate_value_type(self.expires_in, int, "expires_in")
        if self.id_token is not None:
            _validate_value_type(self.id_token, str, "id_token")

    @classmethod
    def from_dict(cls, data: object) -> Self:
        """Собрать данные авторизации из тела ответа IAM, отбросив незнакомые поля.

        :param data: разобранное тело ответа
        :return: данные авторизации
        :raises TypeError: если тело не является объектом, в нем нет обязательных полей или их типы неверны
        """
        if not isinstance(data, dict):
            message = f"Тело ответа должно быть JSON-объектом, получен {type(data).__name__}"
            raise TypeError(message)

        payload = cast("dict[str, object]", data)
        if "access_token" not in payload or "expires_in" not in payload:
            message = "Тело ответа не содержит access_token или expires_in"
            raise TypeError(message)
        return cls(
            access_token=cast("str", payload["access_token"]),
            expires_in=cast("int", payload["expires_in"]),
            id_token=cast("str | None", payload.get("id_token")),
        )


def _validate_value_type(value: object, expected: type[str] | type[int], field: str) -> None:
    if not isinstance(value, expected):
        message = f"Поле {field} должно иметь тип {expected.__name__}, получено {type(value).__name__}"
        raise TypeError(message)


def _public_api_payload(key_id: str, key_secret: str) -> dict[str, str]:
    return {
        "keyId": key_id,
        "secret": key_secret,
    }


def _openid_payload(key_id: str, key_secret: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_id": key_id,
        "client_secret": key_secret,
    }


def _parse_auth_data(response: httpx.Response) -> AuthData:
    """Разобрать ответ сервиса IAM.

    :param response: ответ сервиса IAM
    :raises IAM_AuthError: если код ответа не 200
    :raises IAM_InvalidJsonResponseError: если тело ответа не разбирается в данные авторизации
    :return: данные авторизации
    """
    if response.status_code != codes.OK:
        raise IAM_AuthError(response)

    try:
        return AuthData.from_dict(cast("object", response.json()))
    except (ValueError, TypeError) as e:
        raise IAM_InvalidJsonResponseError(response) from e


class IamHttpClient(HttpClient):
    """HTTP-клиент IAM, использующий публичное API для авторизации."""

    def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Авторизоваться и получить токен доступа к API.

        :param key_id: идентификатор ключа
        :param key_secret: секретный ключ
        :raises IAM_AuthError: если сервис IAM ответил неуспешным кодом
        :raises IAM_InvalidJsonResponseError: если тело ответа не разбирается в данные авторизации
        :return: данные авторизации
        """
        response = self.post(PUBLIC_API_AUTHORIZE_ROUTE, json=_public_api_payload(key_id, key_secret))
        return _parse_auth_data(response)


class IamAsyncHttpClient(AsyncHttpClient):
    """Асинхронный HTTP-клиент IAM, использующий публичное API для авторизации."""

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Авторизоваться и получить токен доступа к API.

        :param key_id: идентификатор ключа
        :param key_secret: секретный ключ
        :raises IAM_AuthError: если сервис IAM ответил неуспешным кодом
        :raises IAM_InvalidJsonResponseError: если тело ответа не разбирается в данные авторизации
        :return: данные авторизации
        """
        response = await self.post(PUBLIC_API_AUTHORIZE_ROUTE, json=_public_api_payload(key_id, key_secret))
        return _parse_auth_data(response)


class IamOpenIdHttpClient(HttpClient):
    """HTTP-клиент IAM, использующий OpenID API для авторизации."""

    def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Авторизоваться и получить токен доступа к API.

        :param key_id: идентификатор ключа
        :param key_secret: секретный ключ
        :raises IAM_AuthError: если сервис IAM ответил неуспешным кодом
        :raises IAM_InvalidJsonResponseError: если тело ответа не разбирается в данные авторизации
        :return: данные авторизации
        """
        response = self.post(OPEN_ID_AUTHORIZE_ROUTE, json=_openid_payload(key_id, key_secret))
        return _parse_auth_data(response)


class IamOpenIdAsyncHttpClient(AsyncHttpClient):
    """Асинхронный HTTP-клиент IAM, использующий OpenID API для авторизации."""

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Авторизоваться и получить токен доступа к API.

        :param key_id: идентификатор ключа
        :param key_secret: секретный ключ
        :raises IAM_AuthError: если сервис IAM ответил неуспешным кодом
        :raises IAM_InvalidJsonResponseError: если тело ответа не разбирается в данные авторизации
        :return: данные авторизации
        """
        response = await self.post(OPEN_ID_AUTHORIZE_ROUTE, json=_openid_payload(key_id, key_secret))
        return _parse_auth_data(response)


IAM_HttpClient = IamHttpClient
IAM_AsyncHttpClient = IamAsyncHttpClient
IAM_OpenID_HttpClient = IamOpenIdHttpClient
IAM_OpenID_AsyncHttpClient = IamOpenIdAsyncHttpClient

IAM_SyncClientT = IAM_HttpClient | IAM_OpenID_HttpClient
IAM_AsyncClientT = IAM_AsyncHttpClient | IAM_OpenID_AsyncHttpClient
