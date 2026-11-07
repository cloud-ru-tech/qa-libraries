import math
from typing import TYPE_CHECKING, cast

import pytest
from explicit_wait import (
    AttemptsExhaustedError,
    InvalidPredicateError,
    TimeoutExpiredError,
    WaitOptions,
    WaitStoppedError,
    configure,
    wait_until,
)

from .fakes import CountingPredicate, FakeClock, ScriptedPredicate
from .matchers import assert_that
from .support import error_from

if TYPE_CHECKING:
    from explicit_wait.types import MaxAttempts


def test_returns_first_truthy_value(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([None, "профиль загружен"])

    result = wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=10.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to("профиль загружен")


def test_calls_predicate_once_when_condition_holds_immediately(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([42])

    wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(predicate.calls).is_equal_to(1)


def test_does_not_sleep_when_condition_holds_immediately(clock: FakeClock) -> None:
    wait_until(
        lambda: "готово",
        options=WaitOptions(timeout_seconds=5.0, sleep_seconds=3.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(clock.sleeps).is_empty()


@pytest.mark.parametrize("falsy", [None, False, 0, "", [], {}, set(), 0.0])
def test_keeps_waiting_on_falsy_result(falsy: object, clock: FakeClock) -> None:
    predicate = ScriptedPredicate([falsy, "наконец-то"])

    result = wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=8.0, sleep_seconds=0.5),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to("наконец-то")


def test_raises_timeout_when_condition_never_holds(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.attempts).is_equal_to(4)


def test_does_not_start_an_attempt_after_the_planned_deadline(clock: FakeClock) -> None:
    predicate = CountingPredicate(truthy_on_call=99)

    error_from(
        lambda: wait_until(
            predicate,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.6),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(predicate.calls).is_equal_to(2)


def test_does_not_start_an_attempt_after_waking_up_late() -> None:
    clock = FakeClock(overshoot=1.0)
    predicate = CountingPredicate(truthy_on_call=99)

    error_from(
        lambda: wait_until(
            predicate,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.6),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(predicate.calls).is_equal_to(1)


def test_sleeps_exactly_by_the_backoff_schedule(clock: FakeClock) -> None:
    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=20.0, sleep_seconds=(1.0, 8.0)),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(clock.sleeps).is_equal_to([1.0, 2.0, 4.0, 8.0])


def test_waits_forever_when_timeout_is_infinite(clock: FakeClock) -> None:
    predicate = CountingPredicate(truthy_on_call=25, value="дождались")

    result = wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=7.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to("дождались")


def test_stops_after_max_attempts(clock: FakeClock) -> None:
    predicate = CountingPredicate(truthy_on_call=99)

    error_from(
        lambda: wait_until(
            predicate,
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=2.0, max_attempts=3),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that(predicate.calls).is_equal_to(3)


def test_expired_deadline_outranks_exhausted_attempts(clock: FakeClock) -> None:
    def burns_the_budget() -> None:
        clock.advance(2.0)

    error = error_from(
        lambda: wait_until(
            burns_the_budget,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=1.0, max_attempts=1),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitStoppedError,
    )

    assert_that(error).is_instance_of(TimeoutExpiredError)


def test_removes_the_configured_attempt_limit_when_given_none(clock: FakeClock) -> None:
    configure(max_attempts=2)
    predicate = CountingPredicate(truthy_on_call=5, value="дождались")

    result = wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=1.0, max_attempts=None),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to("дождались")


def test_ignores_expected_exception(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([ConnectionResetError("соединение сброшено"), "поднялся"])

    result = wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0, expected_exceptions=ConnectionResetError),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to("поднялся")


def test_propagates_unexpected_exception_unchanged(clock: FakeClock) -> None:
    failure = LookupError("нет такого ключа")

    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([failure]),
            options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0, expected_exceptions=ValueError),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        LookupError,
    )

    assert_that(error).is_same_as(failure)


def test_never_swallows_a_nested_wait_error(clock: FakeClock) -> None:
    inner = TimeoutExpiredError(
        waiting_for="вложенное ожидание",
        timeout_seconds=2.0,
        attempts=3,
        elapsed_seconds=2.1,
    )

    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([inner]),
            options=WaitOptions(timeout_seconds=60.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error).is_same_as(inner)


def test_retries_exception_accepted_by_the_filter(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([OSError("503 service unavailable"), "сервис ответил"])

    result = wait_until(
        predicate,
        options=WaitOptions(
            timeout_seconds=9.0,
            sleep_seconds=1.0,
            expected_exceptions=OSError,
            retry_on_exception=lambda error: "503" in str(error),
        ),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_equal_to("сервис ответил")


def test_propagates_exception_rejected_by_the_filter(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([OSError("400 bad request")]),
            options=WaitOptions(
                timeout_seconds=9.0,
                sleep_seconds=1.0,
                expected_exceptions=OSError,
                retry_on_exception=lambda failure: "503" in str(failure),
            ),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        OSError,
    )

    assert_that(str(error)).contains("400")


def test_rejects_zero_timeout(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        wait_until(lambda: True, options=WaitOptions(timeout_seconds=0.0), clock=clock.monotonic, sleeper=clock.sleep)


def test_rejects_negative_timeout(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        wait_until(lambda: True, options=WaitOptions(timeout_seconds=-5.0), clock=clock.monotonic, sleeper=clock.sleep)


def test_rejects_not_a_number_timeout(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        wait_until(
            lambda: True, options=WaitOptions(timeout_seconds=math.nan), clock=clock.monotonic, sleeper=clock.sleep
        )


def test_rejects_zero_max_attempts(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        wait_until(lambda: True, options=WaitOptions(max_attempts=0), clock=clock.monotonic, sleeper=clock.sleep)


@pytest.mark.parametrize("invalid", [1.5, math.nan, math.inf, True])
def test_rejects_max_attempts_that_is_not_a_whole_number(invalid: object, clock: FakeClock) -> None:
    with pytest.raises(TypeError, match="max_attempts"):
        wait_until(
            lambda: True,
            options=WaitOptions(max_attempts=cast("MaxAttempts", invalid)),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        )


def test_rejects_an_asynchronous_predicate(clock: FakeClock) -> None:
    async def ready() -> bool:
        return False

    error = error_from(
        lambda: wait_until(ready, options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0), clock=clock.monotonic),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("async_wait_until")


def test_asynchronous_predicate_is_rejected_even_under_a_broad_exception_filter(clock: FakeClock) -> None:
    async def ready() -> bool:
        return False

    error = error_from(
        lambda: wait_until(
            ready,
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
        ),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("async_wait_until")


def test_deadline_burned_by_the_hook_wins_over_exhausted_attempts(clock: FakeClock) -> None:
    def burn_the_budget(_attempt: object) -> None:
        clock.advance(2.0)

    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.5, max_attempts=1, on_attempt=burn_the_budget),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitStoppedError,
    )

    assert_that(error).is_instance_of(TimeoutExpiredError)


def test_deadline_burned_by_the_hook_is_reported_as_reached(clock: FakeClock) -> None:
    def burn_the_budget(_attempt: object) -> None:
        clock.advance(2.0)

    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0, on_attempt=burn_the_budget),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.deadline_reached).is_true()
