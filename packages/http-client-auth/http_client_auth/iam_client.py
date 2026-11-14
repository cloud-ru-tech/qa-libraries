from dataclasses import dataclass
from typing import Self, cast

import httpx
from http_client import AsyncHttpClient, HttpClient
from httpx import codes

from .exceptions import IAM_AuthError, IAM_InvalidJsonResponseError

PUBLIC_API_AUTHORIZE_ROUTE = "/api/v1/auth/token"
OPEN_ID_AUTHORIZE_ROUTE = "/auth/system/openid/token"

# These IAM fields are not masked by http-client by default.
IAM_SANITIZE_KEYS = ("client_secret", "id_token")


@dataclass(frozen=True, slots=True)
class AuthData:
    """Authentication data received from IAM."""

    access_token: str
    expires_in: int
    id_token: str | None = None

    def __post_init__(self) -> None:
        """Validate IAM response field types.

        :raises TypeError: If response fields have an invalid type.
        """
        _validate_value_type(self.access_token, str, "access_token")
        _validate_value_type(self.expires_in, int, "expires_in")
        if self.id_token is not None:
            _validate_value_type(self.id_token, str, "id_token")

    @classmethod
    def from_dict(cls, data: object) -> Self:
        """Build authentication data from the IAM response body, discarding unknown fields.

        :param data: Parsed response body
        :return: Authentication credentials
        :raises TypeError: If the body is not an object, lacks required fields, or contains invalid field types
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
    """Parse an IAM response.

    :param response: IAM response
    :raises IAM_AuthError: If the response status is not 200
    :raises IAM_InvalidJsonResponseError: If the response body cannot be parsed as authentication data
    :return: Authentication credentials
    """
    if response.status_code != codes.OK:
        raise IAM_AuthError(response)

    try:
        return AuthData.from_dict(cast("object", response.json()))
    except (ValueError, TypeError) as e:
        raise IAM_InvalidJsonResponseError(response) from e


class IamHttpClient(HttpClient):
    """IAM HTTP client using the public API for authentication."""

    def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Authenticate and obtain an API access token.

        :param key_id: Key ID
        :param key_secret: Secret key
        :raises IAM_AuthError: If IAM returns an unsuccessful status
        :raises IAM_InvalidJsonResponseError: If the response body cannot be parsed as authentication data
        :return: Authentication credentials
        """
        response = self.post(PUBLIC_API_AUTHORIZE_ROUTE, json=_public_api_payload(key_id, key_secret))
        return _parse_auth_data(response)


class IamAsyncHttpClient(AsyncHttpClient):
    """Asynchronous IAM HTTP client using the public API for authentication."""

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Authenticate and obtain an API access token.

        :param key_id: Key ID
        :param key_secret: Secret key
        :raises IAM_AuthError: If IAM returns an unsuccessful status
        :raises IAM_InvalidJsonResponseError: If the response body cannot be parsed as authentication data
        :return: Authentication credentials
        """
        response = await self.post(PUBLIC_API_AUTHORIZE_ROUTE, json=_public_api_payload(key_id, key_secret))
        return _parse_auth_data(response)


class IamOpenIdHttpClient(HttpClient):
    """IAM HTTP client using the OpenID API for authentication."""

    def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Authenticate and obtain an API access token.

        :param key_id: Key ID
        :param key_secret: Secret key
        :raises IAM_AuthError: If IAM returns an unsuccessful status
        :raises IAM_InvalidJsonResponseError: If the response body cannot be parsed as authentication data
        :return: Authentication credentials
        """
        response = self.post(OPEN_ID_AUTHORIZE_ROUTE, json=_openid_payload(key_id, key_secret))
        return _parse_auth_data(response)


class IamOpenIdAsyncHttpClient(AsyncHttpClient):
    """Asynchronous IAM HTTP client using the OpenID API for authentication."""

    async def authorize(self, key_id: str, key_secret: str) -> AuthData:
        """Authenticate and obtain an API access token.

        :param key_id: Key ID
        :param key_secret: Secret key
        :raises IAM_AuthError: If IAM returns an unsuccessful status
        :raises IAM_InvalidJsonResponseError: If the response body cannot be parsed as authentication data
        :return: Authentication credentials
        """
        response = await self.post(OPEN_ID_AUTHORIZE_ROUTE, json=_openid_payload(key_id, key_secret))
        return _parse_auth_data(response)


IAM_HttpClient = IamHttpClient
IAM_AsyncHttpClient = IamAsyncHttpClient
IAM_OpenID_HttpClient = IamOpenIdHttpClient
IAM_OpenID_AsyncHttpClient = IamOpenIdAsyncHttpClient

IAM_SyncClientT = IAM_HttpClient | IAM_OpenID_HttpClient
IAM_AsyncClientT = IAM_AsyncHttpClient | IAM_OpenID_AsyncHttpClient
