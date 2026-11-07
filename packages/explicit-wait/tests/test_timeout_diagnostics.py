from explicit_wait import (
    AttemptsExhaustedError,
    TimeoutExpiredError,
    WaitOptions,
    WaitStoppedError,
    wait_until,
)

from .fakes import (
    BrokenStrError,
    FakeClock,
    FalsyWithBrokenRepr,
    FalsyWithHugeRepr,
    ScriptedPredicate,
)
from .matchers import assert_that
from .support import error_from


def test_timeout_error_is_a_builtin_timeout_error() -> None:
    assert_that(issubclass(TimeoutExpiredError, TimeoutError)).is_true()


def test_attempts_exhausted_error_is_a_wait_stopped_error() -> None:
    assert_that(issubclass(AttemptsExhaustedError, WaitStoppedError)).is_true()


def test_base_stopped_error_reports_a_generic_reason() -> None:
    error = WaitStoppedError(
        waiting_for="очередь опустеет",
        timeout_seconds=15.0,
        attempts=4,
        elapsed_seconds=14.2,
    )

    assert_that(str(error)).starts_with("Wait stopped waiting for очередь опустеет")


def test_reports_number_of_attempts(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.attempts).is_equal_to(5)


def test_reports_elapsed_time(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.elapsed_seconds).is_equal_to(4.0)


def test_reports_last_falsy_result(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            list,
            options=WaitOptions(timeout_seconds=3.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.last_result).is_equal_to([])


def test_reports_last_expected_exception(clock: FakeClock) -> None:
    failure = ConnectionError("сервис вернул 503")

    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([ConnectionError("первая ошибка"), failure]),
            options=WaitOptions(timeout_seconds=2.0, sleep_seconds=1.5, expected_exceptions=ConnectionError),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.last_exception).is_same_as(failure)


def test_chains_last_expected_exception_as_cause(clock: FakeClock) -> None:
    failure = ConnectionError("сервис недоступен")

    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([failure]),
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0, expected_exceptions=ConnectionError),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.__cause__).is_same_as(failure)


def test_reports_that_the_deadline_was_reached(clock: FakeClock) -> None:
    def burns_the_budget() -> None:
        clock.advance(5.0)

    error = error_from(
        lambda: wait_until(
            burns_the_budget,
            options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.deadline_reached).is_true()


def test_reports_that_the_next_attempt_did_not_fit(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.deadline_reached).is_false()


def test_explains_that_no_attempt_fits_before_the_deadline(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("No further attempt could start before the 1.0 second deadline")


def test_message_contains_custom_description(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=2.0, sleep_seconds=1.0, message="заказ 42 перейдёт в статус ready"),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("заказ 42 перейдёт в статус ready")


def test_message_falls_back_to_predicate_name(clock: FakeClock) -> None:
    def order_is_ready() -> None:
        return None

    error = error_from(
        lambda: wait_until(
            order_is_ready,
            options=WaitOptions(timeout_seconds=2.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("order_is_ready")


def test_message_does_not_leak_object_address(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=2.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).does_not_contain("0x")


def test_message_reports_last_exception_instead_of_result(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([TimeoutError("апстрим не ответил")]),
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0, expected_exceptions=TimeoutError),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("last exception: TimeoutError: апстрим не ответил")


def test_message_truncates_a_huge_last_result(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            FalsyWithHugeRepr,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("(truncated)")


def test_broken_result_repr_does_not_replace_the_stop_error(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            FalsyWithBrokenRepr,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("<repr failed: RuntimeError>")


def test_broken_exception_str_does_not_replace_the_stop_error(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            ScriptedPredicate([BrokenStrError()]),
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0, expected_exceptions=BrokenStrError),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(str(error)).contains("<str failed: RuntimeError>")


def test_attempts_exhausted_message_reports_the_limit(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=500.0, sleep_seconds=1.0, max_attempts=2),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that(str(error)).contains("All 2 attempts exhausted")


def test_terminal_hook_time_does_not_leak_into_the_error(clock: FakeClock) -> None:
    def burn_the_budget(_attempt: object) -> None:
        clock.advance(2.0)

    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=2.0, on_timeout=burn_the_budget),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(error.elapsed_seconds).is_equal_to(0.0)
