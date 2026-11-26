from typing import TypeGuard, cast

from httpx2 import Request, Response


def is_http_request(value: object) -> TypeGuard[Request]:
    """Check for an HTTPX2 request type.

    :param value: Arbitrary call argument.
    :return: Whether the argument is an HTTPX2 request.
    """
    return isinstance(value, cast("type[object]", Request))


def is_http_response(value: object) -> TypeGuard[Response]:
    """Check for an HTTPX2 response type.

    :param value: Call result.
    :return: Whether the result is an HTTPX2 response.
    """
    return isinstance(value, cast("type[object]", Response))
