"""Retry policy: what to retry and which settings to use."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import httpcore
import httpx
from httpx import Response
from tenacity import RetryCallState, retry_if_result, retry_never
from tenacity.retry import retry_base

from ._types import is_http_response
from .config import NO_OVERRIDES, Config, RetryOverrides, get_config

#: Network errors for which retrying the request makes sense.
RETRYABLE_EXCEPTIONS = (httpx.RequestError, httpcore.NetworkError, httpcore.PoolTimeout)

#: Exceptions excluded from :data:`RETRYABLE_EXCEPTIONS`: these are `RequestError`, but retrying the same
#: request yields exactly the same result while consuming the entire attempt and delay budget.
NON_RETRYABLE_EXCEPTIONS = (
    httpx.TooManyRedirects,
    httpx.UnsupportedProtocol,
    httpx.DecodingError,
    httpx.LocalProtocolError,
)


class retry_transient_errors(retry_base):  # noqa: N801 - tenacity strategy naming convention
    """Retry network errors except those known to be deterministic."""

    def __call__(self, retry_state: RetryCallState) -> bool:
        """Determine whether to retry a failed attempt.

        :param retry_state: State of the latest attempt.
        :return: Whether a retry is required.
        """
        outcome = retry_state.outcome
        if outcome is None or not outcome.failed:
            return False

        error = outcome.exception()

        return isinstance(error, RETRYABLE_EXCEPTIONS) and not isinstance(error, NON_RETRYABLE_EXCEPTIONS)


# Marker on a response rejected by the retry condition. Store it in extensions so callers
# (including RetryError.last_attempt.result()) receive a regular Response.
REJECTED_EXTENSION = "http_client_retries.rejected"

ResponseCondition = Callable[[Response], bool]


@dataclass
class RetryPolicy:
    """Shared retry policy for one client.

    Both options update one instance, so a request uses one tenacity loop
    with a shared attempt budget. Previously each option created its own loop, multiplying
    the limits: `stop_after_attempt(5)` could send up to 25 requests to the transport.
    """

    retry_on_network_errors: bool = False
    conditions: list[ResponseCondition] = field(default_factory=list)
    overrides: RetryOverrides = NO_OVERRIDES

    def rejects(self, response: Response) -> bool:
        """Check whether any condition requests a retry for this response."""
        return any(condition(response) for condition in self.conditions)

    def resolve_config(self) -> Config:
        """Return the current configuration with client overrides applied.

        Read it on every request: `configure()` can change the policy after
        the client has been created.
        """
        return self.overrides.apply_to(get_config())

    def build_strategy(self) -> retry_base:
        """Build a retry condition for tenacity."""
        by_error = retry_transient_errors() if self.retry_on_network_errors else None
        by_result = retry_if_result(self._is_rejected) if self.conditions else None

        if by_error is not None and by_result is not None:
            return by_error | by_result

        return by_error or by_result or retry_never

    def _is_rejected(self, result: object) -> bool:
        # The response condition was checked during the attempt; only read the marker here
        # to avoid calling the user predicate twice.
        if is_http_response(result):
            return bool(cast("dict[str, object]", result.extensions).get(REJECTED_EXTENSION, False))

        return self.rejects(cast("Response", result))


def set_rejected(response: Response, *, rejected: bool) -> None:
    """Set or clear the rejection marker.

    Clearing is required: a response object can be reused between attempts,
    and a stale marker would cause retries for an already accepted response.
    """
    if rejected:
        cast("dict[str, object]", response.extensions)[REJECTED_EXTENSION] = True
    else:
        cast("dict[str, object]", response.extensions).pop(REJECTED_EXTENSION, None)
