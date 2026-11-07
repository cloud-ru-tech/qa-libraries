import asyncio

from explicit_wait import InvalidPredicateError, TimeoutExpiredError, WaitOptions, async_wait_while, wait_while

from .fakes import FakeClock, ScriptedPredicate
from .matchers import assert_that
from .support import error_from


def test_returns_as_soon_as_condition_becomes_falsy(clock: FakeClock) -> None:
    predicate = ScriptedPredicate(["выполняется", "выполняется", None])

    wait_while(
        predicate,
        options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(predicate.calls).is_equal_to(3)


def test_returns_without_sleeping_when_condition_is_already_falsy(clock: FakeClock) -> None:
    wait_while(
        lambda: False,
        options=WaitOptions(timeout_seconds=9.0, sleep_seconds=2.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(clock.sleeps).is_empty()


def test_raises_timeout_while_condition_stays_truthy(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_while(
            lambda: "всё ещё идёт",
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.attempts).is_equal_to(5)


def test_reports_last_truthy_result_in_the_error(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_while(
            lambda: "миграция идёт",
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.last_result).is_equal_to("миграция идёт")


def test_async_variant_returns_when_condition_becomes_falsy(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([1, 0])

    asyncio.run(
        async_wait_while(
            predicate,
            options=WaitOptions(timeout_seconds=9.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(predicate.calls).is_equal_to(2)


def test_rejects_an_asynchronous_predicate(clock: FakeClock) -> None:
    async def running() -> bool:
        return True

    error = error_from(
        lambda: wait_while(running, options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0), clock=clock.monotonic),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("async_wait_while")
