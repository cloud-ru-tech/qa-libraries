import math

import pytest
from explicit_wait import Attempt, AttemptsExhaustedError, TimeoutExpiredError, WaitOptions, wait_until

from .fakes import FakeClock, ScriptedPredicate
from .matchers import assert_that
from .support import error_from


def test_attempt_hook_runs_for_every_attempt_including_falsy_ones(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    wait_until(
        ScriptedPredicate([None, 0, "готово"]),
        options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0, on_attempt=attempts.append),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that([attempt.number for attempt in attempts]).is_equal_to([1, 2, 3])


def test_attempt_hook_receives_the_predicate_result(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    wait_until(
        ScriptedPredicate([None, "версия 2.0.0"]),
        options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0, on_attempt=attempts.append),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(attempts[-1].result).is_equal_to("версия 2.0.0")


def test_attempt_hook_receives_the_expected_exception(clock: FakeClock) -> None:
    failure = ValueError("пока нет данных")
    attempts: list[Attempt] = []

    wait_until(
        ScriptedPredicate([failure, "есть"]),
        options=WaitOptions(
            timeout_seconds=9.0, sleep_seconds=1.0, expected_exceptions=ValueError, on_attempt=attempts.append
        ),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(attempts[0].exception).is_same_as(failure)


def test_attempt_hook_receives_the_planned_sleep(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    wait_until(
        ScriptedPredicate([None, "есть"]),
        options=WaitOptions(timeout_seconds=30.0, sleep_seconds=3.0, on_attempt=attempts.append),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(attempts[0].next_sleep_seconds).is_equal_to(3.0)


def test_final_attempt_has_no_planned_sleep(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    wait_until(
        ScriptedPredicate([None, "есть"]),
        options=WaitOptions(timeout_seconds=30.0, sleep_seconds=3.0, on_attempt=attempts.append),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(attempts[-1].has_no_planned_sleep).is_true()


def test_attempt_hook_failure_is_not_mistaken_for_a_predicate_failure(clock: FakeClock) -> None:
    def failing_hook(_attempt: Attempt) -> None:
        message = "хук сломался"
        raise ValueError(message)

    with pytest.raises(ValueError, match="хук сломался"):
        wait_until(
            lambda: "условие выполнено",
            options=WaitOptions(
                timeout_seconds=9.0, sleep_seconds=1.0, expected_exceptions=ValueError, on_attempt=failing_hook
            ),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        )


def test_timeout_hook_runs_once(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0, on_timeout=attempts.append),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(attempts).is_length(1)


def test_timeout_hook_receives_the_final_attempt_number(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0, on_timeout=attempts.append),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(attempts[0].number).is_equal_to(4)


def test_timeout_hook_does_not_run_when_attempts_are_exhausted(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(
                timeout_seconds=math.inf, sleep_seconds=1.0, max_attempts=2, on_timeout=attempts.append
            ),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that(attempts).is_empty()


def test_exhausted_hook_runs_when_attempts_are_exhausted(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(
                timeout_seconds=math.inf, sleep_seconds=1.0, max_attempts=2, on_attempts_exhausted=attempts.append
            ),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that([attempt.number for attempt in attempts]).is_equal_to([2])


def test_exhausted_hook_does_not_run_on_timeout(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0, on_attempts_exhausted=attempts.append),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(attempts).is_empty()


def test_attempt_hook_does_not_run_for_an_unexpected_exception(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    error_from(
        lambda: wait_until(
            ScriptedPredicate([RuntimeError("совсем неожиданно")]),
            options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0, on_attempt=attempts.append),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        RuntimeError,
    )

    assert_that(attempts).is_empty()
