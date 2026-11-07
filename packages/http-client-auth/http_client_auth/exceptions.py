from typing import cast

import httpx


class IamError(Exception):
    """Базовая ошибка взаимодействия с сервисом IAM."""


class IamAuthError(IamError):
    """Ошибка авторизации в IAM."""

    def __init__(self, response: httpx.Response) -> None:
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        """
        super().__init__(f"Ошибка авторизации в IAM: code = {response.status_code}, body = {response.text}")


class IamInvalidJsonResponseError(IamError):
    """Ошибка валидации JSON ответа от IAM."""

    def __init__(self, response: httpx.Response) -> None:
        # Тело в сообщение не попадает: это успешный ответ IAM, в нем лежит действующий токен доступа.
        """Инициализировать объект.

        :param response: значение настройки ``response``.
        """
        content_type = cast("str", response.headers.get("content-type", "не указан"))
        super().__init__(
            f"Ошибка валидации JSON ответа от IAM: code = {response.status_code}, content-type = {content_type}"
        )


IAM_Error = IamError
IAM_AuthError = IamAuthError
IAM_InvalidJsonResponseError = IamInvalidJsonResponseError
