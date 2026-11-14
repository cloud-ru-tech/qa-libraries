import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Unpack

import httpx
from http_client import AsyncHttpClient, HttpClient, options
from http_client.types import AsyncSendMethod, SendOptions, SyncSendMethod
from http_client_auth import (
    AsyncAuthStore,
    AuthStore,
    IAM_AsyncAuth,
    IAM_AsyncClientT,
    IAM_AsyncHttpClient,
    IAM_Auth,
    IAM_HttpClient,
    IAM_SyncClientT,
)

from . import constants

PayloadBuilder = Callable[[str, str], dict[str, str]]


@dataclass(frozen=True, slots=True)
class SyncIamCase:
    """Synchronous IAM client with the expected authentication request route and body."""

    client_class: type[IAM_SyncClientT]
    route: str
    payload_of: PayloadBuilder


@dataclass(frozen=True, slots=True)
class AsyncIamCase:
    """Asynchronous IAM client with the expected authentication request route and body."""

    client_class: type[IAM_AsyncClientT]
    route: str
    payload_of: PayloadBuilder


def record_sent_requests(calls: list[str]) -> Callable[[SyncSendMethod], SyncSendMethod]:
    """Create a send decorator that records requests passing through it.

    :param calls: List to append each request method and path to
    :return: Decorator for options.with_send_decorator
    """

    def decorator(func: SyncSendMethod) -> SyncSendMethod:
        @wraps(func)
        def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            calls.append(f"{request.method} {request.url.path}")
            return func(request, **kwargs)

        return wrapper

    return decorator


def delay_sent_requests(delay: float) -> Callable[[SyncSendMethod], SyncSendMethod]:
    """Create a send decorator that delays request sending.

    Ensure concurrent calls overlap in time.

    :param delay: Delay in seconds
    :return: Decorator for options.with_send_decorator
    """

    def decorator(func: SyncSendMethod) -> SyncSendMethod:
        @wraps(func)
        def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            time.sleep(delay)
            return func(request, **kwargs)

        return wrapper

    return decorator


def delay_sent_requests_async(delay: float) -> Callable[[AsyncSendMethod], AsyncSendMethod]:
    """Create an asynchronous send decorator that delays request sending.

    :param delay: Delay in seconds
    :return: Decorator for options.with_send_decorator
    """

    def decorator(func: AsyncSendMethod) -> AsyncSendMethod:
        @wraps(func)
        async def wrapper(request: httpx.Request, **kwargs: Unpack[SendOptions]) -> httpx.Response:
            await asyncio.sleep(delay)
            return await func(request, **kwargs)

        return wrapper

    return decorator


@contextmanager
def authorized_client(
    key_id: str,
    key_secret: str,
    store: AuthStore | None = None,
) -> Iterator[HttpClient]:
    """Create an HTTP client authenticated through the IAM public API.

    :param key_id: Key ID
    :param key_secret: Secret key
    :param store: Token store
    :return: Client context manager that closes both connection pools
    """
    with (
        IAM_HttpClient(constants.IAM_URL) as iam_client,
        HttpClient(
            constants.API_URL,
            options.with_auth(IAM_Auth(key_id, key_secret, iam_client, store)),
        ) as client,
    ):
        yield client


@asynccontextmanager
async def async_authorized_client(
    key_id: str,
    key_secret: str,
    store: AsyncAuthStore | None = None,
) -> AsyncIterator[AsyncHttpClient]:
    """Create an asynchronous HTTP client authenticated through the IAM public API.

    :param key_id: Key ID
    :param key_secret: Secret key
    :param store: Token store
    :return: Client context manager that closes both connection pools
    """
    async with (
        IAM_AsyncHttpClient(constants.IAM_URL) as iam_client,
        AsyncHttpClient(
            constants.API_URL,
            options.with_auth(IAM_AsyncAuth(key_id, key_secret, iam_client, store)),
        ) as client,
    ):
        yield client


def iam_auth_response(access_token: str, expires_in: int = 3600) -> dict[str, object]:
    """Build a successful IAM response body.

    :param access_token: Access token returned by IAM
    :param expires_in: Token lifetime in seconds
    :return: Response body
    """
    return {
        "access_token": access_token,
        "id_token": "id-token",
        "expires_in": expires_in,
        "scope": "test_scope",
        "token_type": "Bearer",
    }


def public_api_payload(key_id: str, key_secret: str) -> dict[str, str]:
    """Build an authentication request body for the IAM public API.

    :param key_id: Key ID
    :param key_secret: Secret key
    :return: Request body
    """
    return {"keyId": key_id, "secret": key_secret}


def openid_payload(key_id: str, key_secret: str) -> dict[str, str]:
    """Build an authentication request body for the IAM OpenID API.

    :param key_id: Key ID
    :param key_secret: Secret key
    :return: Request body
    """
    return {
        "grant_type": "client_credentials",
        "client_id": key_id,
        "client_secret": key_secret,
    }
