from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, cast, override

import grpc

from grpc_client.metadata import contains_key

from .base import (
    AsyncMetadataInterceptor,
    AsyncUnaryContinuation,
    ContinuationType,
    MetadataInterceptor,
    aio_call_details,
    call_detail,
    continue_async,
    outcome_code,
    with_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from grpc_client.types import AsyncClientAuth, ClientAuth, MetadataItems

DEFAULT_AUTH_KEY = "authorization"
DEFAULT_AUTH_SCHEME = "Bearer"


class AuthInterceptor(MetadataInterceptor):
    """Интерцептор, подставляющий токен доступа в метаданные запроса.

    Токен запрашивается у переданной реализации `ClientAuth`. Если сервис отвечает `UNAUTHENTICATED`,
    интерцептор просит выпустить новый токен взамен отвергнутого и отправляет унарный запрос повторно.

    Повтор выполняется только для унарных запросов: поток запросов после первой отправки уже исчерпан,
    а для ответного потока итоговый статус известен лишь после вычитывания, поэтому незаметно
    повторить такие вызовы нельзя.

    Если вызывающий код передал собственный заголовок авторизации, интерцептор не вмешивается:
    ни токен не запрашивается, ни повтор не выполняется.
    """

    def __init__(
        self,
        auth: ClientAuth,
        key: str = DEFAULT_AUTH_KEY,
        scheme: str = DEFAULT_AUTH_SCHEME,
        *,
        retry_on_unauthenticated: bool = True,
    ) -> None:
        """Инициализатор.

        :param auth: источник токена доступа
        :param key: имя ключа метаданных, по умолчанию `authorization`
        :param scheme: схема авторизации, по умолчанию `Bearer`
        :param retry_on_unauthenticated: повторять ли унарный запрос с новым токеном после UNAUTHENTICATED
        """
        self._auth = auth
        self._key = key
        self._scheme = scheme
        self._retry_on_unauthenticated = retry_on_unauthenticated

    def metadata_to_add(self, call_details: grpc.ClientCallDetails) -> MetadataItems:
        """Собрать заголовок авторизации, если вызывающий код не задал свой."""
        if self._has_own_auth(call_details):
            return ()
        return self._auth_metadata(self._auth.token())

    @override
    def intercept_unary_unary(
        self,
        continuation: ContinuationType,
        client_call_details: grpc.ClientCallDetails,
        request: object,
    ) -> grpc.CallFuture[object]:
        if self._has_own_auth(client_call_details):
            return cast("grpc.CallFuture[object]", continuation(client_call_details, request))

        # Токен запоминается до отправки: только так реализация авторизации сможет отличить
        # действительно протухший токен от уже обновленного соседним запросом.
        token = self._auth.token()
        outcome = continuation(with_metadata(client_call_details, self._auth_metadata(token)), request)

        if not self._should_retry(outcome):
            return cast("grpc.CallFuture[object]", outcome)

        refreshed = self._auth.refresh(token)
        return cast(
            "grpc.CallFuture[object]",
            continuation(with_metadata(client_call_details, self._auth_metadata(refreshed)), request),
        )

    def _auth_metadata(self, token: str) -> MetadataItems:
        return ((self._key, f"{self._scheme} {token}"),)

    def _should_retry(self, outcome: object) -> bool:
        if not self._retry_on_unauthenticated:
            return False
        return outcome_code(outcome) is grpc.StatusCode.UNAUTHENTICATED

    def _has_own_auth(self, call_details: grpc.ClientCallDetails) -> bool:
        return contains_key(call_detail(call_details, "metadata", None), self._key)


class AsyncAuthInterceptor(AsyncMetadataInterceptor):
    """Асинхронный интерцептор, подставляющий токен доступа в метаданные запроса.

    Токен запрашивается у переданной реализации `AsyncClientAuth`. Если сервис отвечает
    `UNAUTHENTICATED`, интерцептор просит выпустить новый токен взамен отвергнутого и отправляет
    унарный запрос повторно.

    Повтор выполняется только для унарных запросов: поток запросов после первой отправки уже исчерпан,
    а для ответного потока итоговый статус известен лишь после вычитывания, поэтому незаметно
    повторить такие вызовы нельзя.

    Если вызывающий код передал собственный заголовок авторизации, интерцептор не вмешивается:
    ни токен не запрашивается, ни повтор не выполняется.
    """

    def __init__(
        self,
        auth: AsyncClientAuth,
        key: str = DEFAULT_AUTH_KEY,
        scheme: str = DEFAULT_AUTH_SCHEME,
        *,
        retry_on_unauthenticated: bool = True,
    ) -> None:
        """Инициализатор.

        :param auth: источник токена доступа
        :param key: имя ключа метаданных, по умолчанию `authorization`
        :param scheme: схема авторизации, по умолчанию `Bearer`
        :param retry_on_unauthenticated: повторять ли унарный запрос с новым токеном после UNAUTHENTICATED
        """
        self._auth = auth
        self._key = key
        self._scheme = scheme
        self._retry_on_unauthenticated = retry_on_unauthenticated

    async def metadata_to_add(self, call_details: grpc.aio.ClientCallDetails) -> MetadataItems:
        """Собрать заголовок авторизации, если вызывающий код не задал свой."""
        if self._has_own_auth(call_details):
            return ()
        return self._auth_metadata(await self._auth.token())

    @override
    async def intercept_unary_unary(
        self,
        continuation: AsyncUnaryContinuation,
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
        if self._has_own_auth(client_call_details):
            return await continue_async(continuation, client_call_details, request)

        token = await self._auth.token()
        call: object = await continue_async(
            continuation, aio_call_details(client_call_details, self._auth_metadata(token)), request
        )

        if not await self._should_retry(call):
            return call

        refreshed = await self._auth.refresh(token)
        return await continue_async(
            continuation, aio_call_details(client_call_details, self._auth_metadata(refreshed)), request
        )

    def _auth_metadata(self, token: str) -> MetadataItems:
        return ((self._key, f"{self._scheme} {token}"),)

    async def _should_retry(self, call: object) -> bool:
        if not self._retry_on_unauthenticated:
            return False

        code = cast("Callable[[], Awaitable[grpc.StatusCode] | grpc.StatusCode] | None", getattr(call, "code", None))
        if not callable(code):
            return False

        try:
            result = code()
            status = await result if inspect.isawaitable(result) else result
        except grpc.aio.AioRpcError as error:
            status = error.code()

        return status is grpc.StatusCode.UNAUTHENTICATED

    def _has_own_auth(self, call_details: grpc.aio.ClientCallDetails) -> bool:
        return contains_key(call_detail(call_details, "metadata", None), self._key)


__all__ = ["AsyncAuthInterceptor", "AuthInterceptor"]
