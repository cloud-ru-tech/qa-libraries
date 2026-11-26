"""Network error cases for which the request should be retried.

Each case returns a pair: the error and its occurrence count before a successful response.
"""

from typing import Protocol, cast

import httpcore2
import httpx2
from pytest_cases import case


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_TypedDecorator", case(id="httpx2_request_error"))
def case_httpx2_request_error() -> tuple[Exception, int]:
    return httpx2.RequestError("transport failed", request=httpx2.Request("GET", "https://orders.internal/v1")), 2


@cast("_TypedDecorator", case(id="httpx2_connect_error"))
def case_httpx2_connect_error() -> tuple[Exception, int]:
    return httpx2.ConnectError("connection refused", request=httpx2.Request("POST", "https://payments.test/charge")), 2


@cast("_TypedDecorator", case(id="httpx2_timeout_exception"))
def case_httpx2_timeout_exception() -> tuple[Exception, int]:
    return httpx2.TimeoutException(
        "deadline exceeded", request=httpx2.Request("PUT", "https://search.example/index")
    ), 2


@cast("_TypedDecorator", case(id="httpx2_read_error"))
def case_httpx2_read_error() -> tuple[Exception, int]:
    return httpx2.ReadError("body truncated", request=httpx2.Request("GET", "https://media.internal/asset")), 2


@cast("_TypedDecorator", case(id="httpcore2_network_error"))
def case_httpcore2_network_error() -> tuple[Exception, int]:
    return httpcore2.NetworkError("interface down"), 1


@cast("_TypedDecorator", case(id="httpcore2_pool_timeout"))
def case_httpcore2_pool_timeout() -> tuple[Exception, int]:
    return httpcore2.PoolTimeout("pool exhausted"), 1


@cast("_TypedDecorator", case(id="too_many_redirects"))
def deterministic_too_many_redirects() -> Exception:
    """Represent retries following the same redirect chain and reaching the same limit."""
    return httpx2.TooManyRedirects("redirect loop", request=httpx2.Request("GET", "https://loop.test/a"))


@cast("_TypedDecorator", case(id="unsupported_protocol"))
def deterministic_unsupported_protocol() -> Exception:
    """Retrying does not change the URL scheme."""
    return httpx2.UnsupportedProtocol("scheme not supported", request=httpx2.Request("GET", "https://odd.test/a"))


@cast("_TypedDecorator", case(id="decoding_error"))
def deterministic_decoding_error() -> Exception:
    """Represent a server returning the same unreadable body on retries."""
    return httpx2.DecodingError("broken encoding", request=httpx2.Request("GET", "https://codec.test/a"))


@cast("_TypedDecorator", case(id="local_protocol_error"))
def deterministic_local_protocol_error() -> Exception:
    """Represent an incorrectly built request that retries would build the same way."""
    return httpx2.LocalProtocolError("malformed request")
