from typing import Protocol, cast

from http_client_auth import (
    IAM_AsyncHttpClient,
    IAM_HttpClient,
    IAM_OpenID_AsyncHttpClient,
    IAM_OpenID_HttpClient,
)
from http_client_auth.iam_client import OPEN_ID_AUTHORIZE_ROUTE, PUBLIC_API_AUTHORIZE_ROUTE
from pytest_cases import case

from .factories import AsyncIamCase, SyncIamCase, openid_payload, public_api_payload


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_TypedDecorator", case(id="public_api", tags=("sync",)))
def case_public_api() -> SyncIamCase:
    return SyncIamCase(IAM_HttpClient, PUBLIC_API_AUTHORIZE_ROUTE, public_api_payload)


@cast("_TypedDecorator", case(id="openid_api", tags=("sync",)))
def case_openid_api() -> SyncIamCase:
    return SyncIamCase(IAM_OpenID_HttpClient, OPEN_ID_AUTHORIZE_ROUTE, openid_payload)


@cast("_TypedDecorator", case(id="public_api", tags=("async",)))
def case_async_public_api() -> AsyncIamCase:
    return AsyncIamCase(IAM_AsyncHttpClient, PUBLIC_API_AUTHORIZE_ROUTE, public_api_payload)


@cast("_TypedDecorator", case(id="openid_api", tags=("async",)))
def case_async_openid_api() -> AsyncIamCase:
    return AsyncIamCase(IAM_OpenID_AsyncHttpClient, OPEN_ID_AUTHORIZE_ROUTE, openid_payload)
