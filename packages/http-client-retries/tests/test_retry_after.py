"""Delay between attempts based on the response `Retry-After` header."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from http_client_retries import configure
from http_client_retries.config import Config
from http_client_retries.retry_after import parse_retry_after, wait_retry_after
from tenacity import wait_fixed

from tests.assertions import assert_that
from tests.fakes import retry_state_after, retry_state_after_error


def test_reads_delay_given_in_seconds() -> None:
    assert_that(parse_retry_after("120")).is_equal_to(120.0)


def test_reads_zero_delay() -> None:
    assert_that(parse_retry_after("0")).is_equal_to(0.0)


def test_rejects_negative_delay() -> None:
    assert_that(parse_retry_after("-30")).is_none()


def test_reads_delay_given_as_http_date() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    deadline = now + timedelta(seconds=45)

    assert_that(parse_retry_after(deadline.strftime("%a, %d %b %Y %H:%M:%S GMT"), now)).is_equal_to(45.0)


def test_clamps_past_http_date_to_zero() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    passed = now - timedelta(hours=2)

    assert_that(parse_retry_after(passed.strftime("%a, %d %b %Y %H:%M:%S GMT"), now)).is_equal_to(0.0)


def test_rejects_unreadable_delay() -> None:
    assert_that(parse_retry_after("as soon as possible")).is_none()


def test_rejects_empty_delay() -> None:
    assert_that(parse_retry_after("   ")).is_none()


def test_rejects_infinite_delay() -> None:
    assert_that(parse_retry_after("inf")).is_none()


def test_reads_http_date_given_without_timezone() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0)  # noqa: DTZ001 - The test specifically checks a date without a timezone
    deadline = now + timedelta(seconds=30)

    assert_that(parse_retry_after(deadline.strftime("%a, %d %b %Y %H:%M:%S GMT"), now)).is_equal_to(30.0)


def test_rejects_negative_upper_bound() -> None:
    with pytest.raises(ValueError, match="неотрицательным"):
        wait_retry_after(fallback=wait_fixed(1), maximum=-1)


def test_rejects_infinite_upper_bound() -> None:
    with pytest.raises(ValueError, match="конечным"):
        wait_retry_after(fallback=wait_fixed(1), maximum=float("inf"))


def test_rejects_negative_max_retry_after_in_configuration() -> None:
    with pytest.raises(ValueError, match="max_retry_after"):
        configure(options=Config(max_retry_after=-5))


def test_waits_as_long_as_server_asked() -> None:
    strategy = wait_retry_after(fallback=wait_fixed(7), maximum=300)
    throttled = httpx.Response(429, headers={"Retry-After": "12"})

    assert_that(strategy(retry_state_after(throttled))).is_equal_to(12.0)


def test_caps_delay_requested_by_server() -> None:
    strategy = wait_retry_after(fallback=wait_fixed(7), maximum=30)
    throttled = httpx.Response(503, headers={"Retry-After": "3600"})

    assert_that(strategy(retry_state_after(throttled))).is_equal_to(30.0)


def test_falls_back_when_server_stays_silent() -> None:
    strategy = wait_retry_after(fallback=wait_fixed(9), maximum=300)

    assert_that(strategy(retry_state_after(httpx.Response(500)))).is_equal_to(9.0)


def test_falls_back_when_header_is_unreadable() -> None:
    strategy = wait_retry_after(fallback=wait_fixed(4), maximum=300)
    confused = httpx.Response(503, headers={"Retry-After": "tomorrow-ish"})

    assert_that(strategy(retry_state_after(confused))).is_equal_to(4.0)


def test_falls_back_when_attempt_raised() -> None:
    strategy = wait_retry_after(fallback=wait_fixed(3), maximum=300)
    broken = httpx.ConnectError("no route", request=httpx.Request("GET", "https://quotas.test/limit"))

    assert_that(strategy(retry_state_after_error(broken))).is_equal_to(3.0)
