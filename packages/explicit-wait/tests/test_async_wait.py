import asyncio

import pytest
from explicit_wait import (
    Attempt,
    AttemptsExhaustedError,
    TimeoutExpiredError,
    WaitOptions,
    async_wait_or_none,
    async_wait_until,
    async_wait_while,
)

from .fakes import CountingPredicate, FakeClock, ScriptedPredicate, generator_based_awaitable
from .matchers import assert_that
from .support import async_error_from

LONG_TIMEOUT = 1000.0


def test_awaits_an_async_predicate(clock: FakeClock) -> None:
    async def cluster_is_ready() -> str | None:
        return "кластер поднят"

    result = asyncio.run(
        async_wait_until(
            cluster_is_ready,
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_equal_to("кластер поднят")


def test_accepts_a_plain_predicate(clock: FakeClock) -> None:
    result = asyncio.run(
        async_wait_until(
            lambda: "обычная функция тоже подходит",
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_equal_to("обычная функция тоже подходит")


def test_awaits_a_generator_based_awaitable(clock: FakeClock) -> None:
    result = asyncio.run(
        async_wait_until(
            lambda: generator_based_awaitable("старый awaitable"),
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_equal_to("старый awaitable")


def test_retries_an_async_predicate_until_it_succeeds(clock: FakeClock) -> None:
    predicate = CountingPredicate(truthy_on_call=4, value="реплика догнала")

    async def replica_caught_up() -> object:
        return predicate()

    result = asyncio.run(
        async_wait_until(
            replica_caught_up,
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_equal_to("реплика догнала")


def test_raises_timeout_when_condition_never_holds(clock: FakeClock) -> None:
    error = async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.attempts).is_equal_to(5)


def test_sleeps_by_the_backoff_schedule(clock: FakeClock) -> None:
    async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=20.0, sleep_seconds=(1.0, 8.0)),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(clock.sleeps).is_equal_to([1.0, 2.0, 4.0, 8.0])


def test_does_not_start_an_attempt_after_waking_up_late() -> None:
    clock = FakeClock(overshoot=1.0)
    predicate = CountingPredicate(truthy_on_call=99)

    async_error_from(
        async_wait_until(
            predicate,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.6),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(predicate.calls).is_equal_to(1)


def test_stops_after_max_attempts(clock: FakeClock) -> None:
    error = async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=LONG_TIMEOUT, sleep_seconds=1.0, max_attempts=2),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that(error.attempts).is_equal_to(2)


def test_ignores_expected_exception(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([ConnectionRefusedError("порт закрыт"), "порт открылся"])

    async def connect() -> object:
        return predicate()

    result = asyncio.run(
        async_wait_until(
            connect,
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0, expected_exceptions=ConnectionRefusedError),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_equal_to("порт открылся")


def test_retries_exception_accepted_by_the_filter(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([OSError("503 service unavailable"), "сервис ответил"])

    async def call_service() -> object:
        return predicate()

    result = asyncio.run(
        async_wait_until(
            call_service,
            options=WaitOptions(
                timeout_seconds=30.0,
                sleep_seconds=1.0,
                expected_exceptions=OSError,
                retry_on_exception=lambda error: "503" in str(error),
            ),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_equal_to("сервис ответил")


def test_propagates_exception_rejected_by_the_filter(clock: FakeClock) -> None:
    predicate = ScriptedPredicate([OSError("400 bad request")])

    async def call_service() -> object:
        return predicate()

    error = async_error_from(
        async_wait_until(
            call_service,
            options=WaitOptions(
                timeout_seconds=30.0,
                sleep_seconds=1.0,
                expected_exceptions=OSError,
                retry_on_exception=lambda failure: "503" in str(failure),
            ),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        OSError,
    )

    assert_that(str(error)).contains("400")


def test_or_none_returns_none_on_timeout(clock: FakeClock) -> None:
    result = asyncio.run(
        async_wait_or_none(
            lambda: None,
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_none()


def test_never_swallows_a_nested_wait_error(clock: FakeClock) -> None:
    inner = TimeoutExpiredError(
        waiting_for="вложенное ожидание",
        timeout_seconds=2.0,
        attempts=3,
        elapsed_seconds=2.1,
    )
    predicate = ScriptedPredicate([inner])

    async def nested() -> object:
        return predicate()

    error = async_error_from(
        async_wait_or_none(
            nested,
            options=WaitOptions(timeout_seconds=60.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error).is_same_as(inner)


def test_lets_background_tasks_make_the_condition_true(clock: FakeClock) -> None:
    state = {"ready": False}

    async def flip_later() -> None:
        await asyncio.sleep(0)
        state["ready"] = True

    async def scenario() -> object:
        task = asyncio.create_task(flip_later())
        result = await async_wait_until(
            lambda: state["ready"],
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        )
        await task
        return result

    assert_that(asyncio.run(scenario())).is_true()


def test_while_raises_timeout_when_condition_stays_truthy(clock: FakeClock) -> None:
    error = async_error_from(
        async_wait_while(
            lambda: "всё ещё выполняется",
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.attempts).is_equal_to(4)


def test_propagates_unexpected_exception(clock: FakeClock) -> None:
    failure = KeyError("нет ключа в ответе")

    error = async_error_from(
        async_wait_until(
            ScriptedPredicate([failure]),
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0, expected_exceptions=ValueError),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        KeyError,
    )

    assert_that(error).is_same_as(failure)


def test_attempt_hook_runs_for_every_attempt(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    asyncio.run(
        async_wait_until(
            ScriptedPredicate([None, None, "готово"]),
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0, on_attempt=attempts.append),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that([attempt.number for attempt in attempts]).is_equal_to([1, 2, 3])


def test_timeout_hook_runs_once(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=3.0, sleep_seconds=1.0, on_timeout=attempts.append),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(attempts).is_length(1)


def test_exhausted_hook_runs_when_attempts_are_exhausted(clock: FakeClock) -> None:
    attempts: list[Attempt] = []

    async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(
                timeout_seconds=LONG_TIMEOUT, sleep_seconds=1.0, max_attempts=2, on_attempts_exhausted=attempts.append
            ),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that([attempt.number for attempt in attempts]).is_equal_to([2])


def test_does_not_swallow_task_cancellation(clock: FakeClock) -> None:
    def never_ready() -> str | None:
        return None

    async def scenario() -> None:
        task = asyncio.create_task(
            async_wait_until(
                never_ready,
                options=WaitOptions(timeout_seconds=LONG_TIMEOUT, sleep_seconds=1.0, expected_exceptions=Exception),
                clock=clock.monotonic,
                sleeper=clock.async_sleep,
            ),
        )
        await asyncio.sleep(0)
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scenario())


def test_deadline_burned_by_the_hook_prevents_the_planned_sleep(clock: FakeClock) -> None:
    def burn_the_budget(_attempt: Attempt) -> None:
        clock.advance(1.0)

    async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.5, on_attempt=burn_the_budget),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(clock.sleeps).is_empty()


def test_deadline_burned_by_the_hook_wins_over_exhausted_attempts(clock: FakeClock) -> None:
    def burn_the_budget(_attempt: Attempt) -> None:
        clock.advance(2.0)

    error = async_error_from(
        async_wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.5, max_attempts=1, on_attempt=burn_the_budget),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.deadline_reached).is_true()
