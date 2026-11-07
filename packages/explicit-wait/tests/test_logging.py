import logging

import pytest
from explicit_wait import AllOf, InvalidPredicateError, TimeoutExpiredError, WaitOptions, wait_until

from .fakes import (
    BrokenStrError,
    FakeClock,
    FalsyWithBrokenRepr,
    ScriptedPredicate,
    started_awaitable_that_refuses_to_close,
)
from .matchers import assert_that
from .support import error_from


def test_reports_every_attempt_at_debug_level(clock: FakeClock, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="explicit_wait.loop"):
        error_from(
            lambda: wait_until(
                lambda: None,
                options=WaitOptions(timeout_seconds=3.0, sleep_seconds=1.0),
                clock=clock.monotonic,
                sleeper=clock.sleep,
            ),
            TimeoutExpiredError,
        )

    assert_that(caplog.records).is_length(3)


def test_broken_result_repr_does_not_break_debug_logging(
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="explicit_wait.loop"):
        error_from(
            lambda: wait_until(
                FalsyWithBrokenRepr,
                options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0),
                clock=clock.monotonic,
                sleeper=clock.sleep,
            ),
            TimeoutExpiredError,
        )

    assert_that(caplog.records[0].getMessage()).contains("<repr failed: RuntimeError>")


def test_broken_exception_str_does_not_break_debug_logging(
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="explicit_wait.loop"):
        error_from(
            lambda: wait_until(
                ScriptedPredicate([BrokenStrError()]),
                options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0, expected_exceptions=BrokenStrError),
                clock=clock.monotonic,
                sleeper=clock.sleep,
            ),
            TimeoutExpiredError,
        )

    assert_that(caplog.records[0].getMessage()).contains("<str failed: RuntimeError>")


def test_failing_awaitable_cleanup_is_only_logged(caplog: pytest.LogCaptureFixture) -> None:
    awaitable = started_awaitable_that_refuses_to_close()

    with caplog.at_level(logging.DEBUG, logger="explicit_wait.validators"):
        error_from(AllOf([lambda: awaitable]), InvalidPredicateError)

    assert_that(caplog.records[0].getMessage()).contains("Не удалось закрыть awaitable")
