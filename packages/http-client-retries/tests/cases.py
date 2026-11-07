"""Наборы сетевых ошибок, при которых запрос должен повторяться.

Каждый кейс возвращает пару (ошибка, сколько раз она повторится до успешного ответа).
"""

from typing import Protocol, cast

import httpcore
import httpx
from pytest_cases import case


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_TypedDecorator", case(id="httpx_request_error"))
def case_httpx_request_error() -> tuple[Exception, int]:
    return httpx.RequestError("transport failed", request=httpx.Request("GET", "https://orders.internal/v1")), 2


@cast("_TypedDecorator", case(id="httpx_connect_error"))
def case_httpx_connect_error() -> tuple[Exception, int]:
    return httpx.ConnectError("connection refused", request=httpx.Request("POST", "https://payments.test/charge")), 2


@cast("_TypedDecorator", case(id="httpx_timeout_exception"))
def case_httpx_timeout_exception() -> tuple[Exception, int]:
    return httpx.TimeoutException("deadline exceeded", request=httpx.Request("PUT", "https://search.example/index")), 2


@cast("_TypedDecorator", case(id="httpx_read_error"))
def case_httpx_read_error() -> tuple[Exception, int]:
    return httpx.ReadError("body truncated", request=httpx.Request("GET", "https://media.internal/asset")), 2


@cast("_TypedDecorator", case(id="httpcore_network_error"))
def case_httpcore_network_error() -> tuple[Exception, int]:
    return httpcore.NetworkError("interface down"), 1


@cast("_TypedDecorator", case(id="httpcore_pool_timeout"))
def case_httpcore_pool_timeout() -> tuple[Exception, int]:
    return httpcore.PoolTimeout("pool exhausted"), 1


@cast("_TypedDecorator", case(id="too_many_redirects"))
def deterministic_too_many_redirects() -> Exception:
    """Повтор пойдёт по той же цепочке редиректов и упрётся в тот же предел."""
    return httpx.TooManyRedirects("redirect loop", request=httpx.Request("GET", "https://loop.test/a"))


@cast("_TypedDecorator", case(id="unsupported_protocol"))
def deterministic_unsupported_protocol() -> Exception:
    """Схема URL не изменится от повтора."""
    return httpx.UnsupportedProtocol("scheme not supported", request=httpx.Request("GET", "https://odd.test/a"))


@cast("_TypedDecorator", case(id="decoding_error"))
def deterministic_decoding_error() -> Exception:
    """Сервер вернёт то же нечитаемое тело."""
    return httpx.DecodingError("broken encoding", request=httpx.Request("GET", "https://codec.test/a"))


@cast("_TypedDecorator", case(id="local_protocol_error"))
def deterministic_local_protocol_error() -> Exception:
    """Запрос неверно собран на нашей стороне — повтор соберёт его так же."""
    return httpx.LocalProtocolError("malformed request")
