"""Use the response `Retry-After` header to choose delays between attempts."""

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import cast

from tenacity import RetryCallState
from tenacity.wait import WaitBaseT, wait_base

from ._types import is_http_response

RETRY_AFTER_HEADER = "Retry-After"


def parse_retry_after(value: str, now: datetime | None = None) -> float | None:
    """Parse `Retry-After` as seconds or an HTTP date.

    Return a delay in seconds, or `None` for an unparseable value. A negative number of
    seconds is invalid: the specification requires a nonnegative delay, and substituting
    an immediate retry would invent behavior.

    :param now: Reference time for an HTTP date. Interpret dates without a timezone as UTC.
    """
    raw = value.strip()
    if not raw:
        return None

    seconds = _parse_seconds(raw)
    if seconds is not None:
        return seconds

    return _parse_http_date(raw, _as_aware(now) if now is not None else datetime.now(UTC))


def _as_aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _parse_seconds(raw: str) -> float | None:
    try:
        seconds = float(raw)
    except ValueError:
        return None

    if not math.isfinite(seconds) or seconds < 0:
        return None

    return seconds


def _parse_http_date(raw: str, now: datetime) -> float | None:
    try:
        deadline = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None

    # A past date validly means retry immediately, unlike negative seconds.
    return max(0.0, (_as_aware(deadline) - now).total_seconds())


class wait_retry_after(wait_base):  # noqa: N801 - tenacity strategy naming convention
    """Wait as requested by the server, or use the fallback strategy.

    Cap the `Retry-After` delay: the server may request an hour,
    but the caller cannot remain blocked that long.
    """

    def __init__(self, fallback: WaitBaseT, maximum: float) -> None:
        """Initialize the object.

        :param fallback: Value of ``fallback``.
        :param maximum: Value of ``maximum``.
        """
        if not math.isfinite(maximum) or maximum < 0:
            message = f"Верхняя граница паузы должна быть конечным неотрицательным числом, получено {maximum!r}"
            raise ValueError(message)

        self._fallback = fallback
        self._maximum = maximum

    def __call__(self, retry_state: RetryCallState) -> float:
        """Determine the delay before the next attempt.

        :param retry_state: State of the latest attempt.
        :return: Delay in seconds.
        """
        requested = self._requested_delay(retry_state)
        if requested is None:
            return self._fallback(retry_state)

        return min(requested, self._maximum)

    def _requested_delay(self, retry_state: RetryCallState) -> float | None:
        outcome = retry_state.outcome
        if outcome is None or outcome.failed:
            return None

        response = cast("object", outcome.result())
        if not is_http_response(response):
            return None

        header = cast("str | None", response.headers.get(RETRY_AFTER_HEADER))

        return parse_retry_after(header) if header else None
