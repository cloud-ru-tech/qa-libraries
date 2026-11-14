from typing import TypeGuard, cast

from httpx import Request, Response


def is_http_request(value: object) -> TypeGuard[Request]:
    """Check for an HTTPX request type.

    :param value: Arbitrary call argument.
    :return: Whether the argument is an HTTPX request.
    """
    return isinstance(value, cast("type[object]", Request))


def is_http_response(value: object) -> TypeGuard[Response]:
    """Check for an HTTPX response type.

    :param value: Call result.
    :return: Whether the result is an HTTPX response.
    """
    return isinstance(value, cast("type[object]", Response))
