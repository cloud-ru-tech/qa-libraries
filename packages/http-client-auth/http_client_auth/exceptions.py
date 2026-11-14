from typing import cast

import httpx


class IamError(Exception):
    """Base error for IAM interactions."""


class IamAuthError(IamError):
    """IAM authentication error."""

    def __init__(self, response: httpx.Response) -> None:
        """Initialize the object.

        :param response: Value of ``response``.
        """
        super().__init__(f"Ошибка авторизации в IAM: code = {response.status_code}, body = {response.text}")


class IamInvalidJsonResponseError(IamError):
    """IAM JSON response validation error."""

    def __init__(self, response: httpx.Response) -> None:
        # Exclude the body from the message: a successful IAM response contains a valid access token.
        """Initialize the object.

        :param response: Value of ``response``.
        """
        content_type = cast("str", response.headers.get("content-type", "не указан"))
        super().__init__(
            f"Ошибка валидации JSON ответа от IAM: code = {response.status_code}, content-type = {content_type}"
        )


IAM_Error = IamError
IAM_AuthError = IamAuthError
IAM_InvalidJsonResponseError = IamInvalidJsonResponseError
