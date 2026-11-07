from explicit_wait import (
    AttemptsExhaustedError,
    InvalidPredicateError,
    TimeoutExpiredError,
    WaitError,
    WaitOptions,
    wait_or_none,
)

from .fakes import CountingPredicate, FakeClock, ScriptedPredicate
from .matchers import assert_that
from .support import error_from


def test_returns_first_truthy_value(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([None, {"status": "ready"}])

    result = wait_or_none(
        predicate,
        options=WaitOptions(timeout_seconds=6.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to({"status": "ready"})


def test_returns_none_when_condition_never_holds(clock: FakeClock) -> None:
    result = wait_or_none(
        lambda: None,
        options=WaitOptions(timeout_seconds=3.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_none()


def test_returns_none_when_attempts_run_out(clock: FakeClock) -> None:
    result = wait_or_none(
        CountingPredicate(truthy_on_call=50),
        options=WaitOptions(timeout_seconds=500.0, sleep_seconds=1.0, max_attempts=4),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_none()


def test_does_not_swallow_timeout_raised_by_the_predicate(clock: FakeClock) -> None:
    inner_failure = TimeoutExpiredError(
        waiting_for="вложенная операция",
        timeout_seconds=3.0,
        attempts=7,
        elapsed_seconds=3.1,
    )

    error = error_from(
        lambda: wait_or_none(
            ScriptedPredicate([inner_failure]),
            options=WaitOptions(timeout_seconds=60.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error).is_same_as(inner_failure)


def test_does_not_swallow_a_nested_timeout_under_a_broad_exception_filter(clock: FakeClock) -> None:
    inner_failure = TimeoutExpiredError(
        waiting_for="вложенная операция",
        timeout_seconds=3.0,
        attempts=7,
        elapsed_seconds=3.1,
    )

    error = error_from(
        lambda: wait_or_none(
            ScriptedPredicate([inner_failure]),
            options=WaitOptions(timeout_seconds=60.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error).is_same_as(inner_failure)


def test_does_not_swallow_nested_exhausted_attempts_under_a_broad_exception_filter(clock: FakeClock) -> None:
    inner_failure = AttemptsExhaustedError(
        waiting_for="вложенная операция",
        timeout_seconds=10.0,
        attempts=3,
        elapsed_seconds=1.0,
    )

    error = error_from(
        lambda: wait_or_none(
            ScriptedPredicate([inner_failure]),
            options=WaitOptions(timeout_seconds=60.0, sleep_seconds=1.0, expected_exceptions=WaitError),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that(error).is_same_as(inner_failure)


def test_calls_timeout_hook_once(clock: FakeClock) -> None:
    hook_calls: list[int] = []

    wait_or_none(
        lambda: 0,
        options=WaitOptions(
            timeout_seconds=3.0, sleep_seconds=1.0, on_timeout=lambda attempt: hook_calls.append(attempt.number)
        ),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(hook_calls).is_length(1)


def test_rejects_an_asynchronous_predicate(clock: FakeClock) -> None:
    async def ready() -> bool:
        return False

    error = error_from(
        lambda: wait_or_none(ready, options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0), clock=clock.monotonic),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("async_wait_or_none")
