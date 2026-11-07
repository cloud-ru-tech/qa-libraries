import math
from threading import Event, Thread

from explicit_wait import TimeoutExpiredError, WaitCancelledError, WaitOptions, wait_or_none, wait_until

from .fakes import CountingPredicate, EventCancelledOnWait, FakeClock
from .matchers import assert_that
from .support import error_from


def test_does_not_call_the_predicate_when_already_cancelled(clock: FakeClock) -> None:
    predicate = CountingPredicate(truthy_on_call=1)
    cancel = Event()
    cancel.set()

    error_from(
        lambda: wait_until(
            predicate,
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            cancel_event=cancel,
            clock=clock.monotonic,
        ),
        WaitCancelledError,
    )

    assert_that(predicate.calls).is_equal_to(0)


def test_stops_waiting_once_cancelled_between_attempts(clock: FakeClock) -> None:
    cancel = Event()

    def cancel_after_first_look() -> None:
        cancel.set()

    error = error_from(
        lambda: wait_until(
            cancel_after_first_look,
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            cancel_event=cancel,
            clock=clock.monotonic,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(1)


def test_cancellation_outranks_exhausted_attempts(clock: FakeClock) -> None:
    cancel = Event()

    def cancel_on_the_last_attempt() -> None:
        cancel.set()

    error = error_from(
        lambda: wait_until(
            cancel_on_the_last_attempt,
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=1.0, max_attempts=1),
            cancel_event=cancel,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(1)


def test_cancellation_is_not_converted_to_none_by_wait_or_none(clock: FakeClock) -> None:
    cancel = Event()
    cancel.set()

    error = error_from(
        lambda: wait_or_none(
            lambda: None,
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            cancel_event=cancel,
            clock=clock.monotonic,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(0)


def test_untouched_event_does_not_interrupt_the_wait(clock: FakeClock) -> None:
    predicate = CountingPredicate(truthy_on_call=3, value="дождались")

    result = wait_until(
        predicate,
        options=WaitOptions(timeout_seconds=30.0, sleep_seconds=0.001),
        cancel_event=Event(),
        clock=clock.monotonic,
    )

    assert_that(result).is_equal_to("дождались")


def test_cancellation_outranks_a_successful_attempt(clock: FakeClock) -> None:
    cancel = Event()

    def succeeds_and_cancels() -> str:
        cancel.set()
        return "ready"

    error = error_from(
        lambda: wait_until(
            succeeds_and_cancels,
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=1.0, max_attempts=1),
            cancel_event=cancel,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(1)


def test_cancellation_from_another_thread_outranks_a_successful_attempt(clock: FakeClock) -> None:
    cancel = Event()
    started = Event()

    def succeeds_slowly() -> str:
        started.set()
        cancel.wait(timeout=5.0)
        return "ready"

    def cancel_once_started() -> None:
        started.wait(timeout=5.0)
        cancel.set()

    canceller = Thread(target=cancel_once_started)
    canceller.start()
    error = error_from(
        lambda: wait_until(
            succeeds_slowly,
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=1.0, max_attempts=1),
            cancel_event=cancel,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitCancelledError,
    )
    canceller.join()

    assert_that(error.attempts).is_equal_to(1)


def test_cancellation_during_the_attempt_hook_stops_the_wait(clock: FakeClock) -> None:
    cancel = Event()

    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=1.0, on_attempt=lambda _attempt: cancel.set()),
            cancel_event=cancel,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(1)


def test_attempt_hook_that_burns_the_deadline_prevents_the_planned_sleep(clock: FakeClock) -> None:
    def burn_the_budget(_attempt: object) -> None:
        clock.advance(1.0)

    error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=1.0, sleep_seconds=0.5, on_attempt=burn_the_budget),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(clock.sleeps).is_empty()


def test_cancellation_during_the_sleep_stops_the_wait(clock: FakeClock) -> None:
    cancel = EventCancelledOnWait()

    error = error_from(
        lambda: wait_until(
            lambda: None,
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=5.0),
            cancel_event=cancel,
            clock=clock.monotonic,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(1)


def test_cancellation_from_the_attempt_hook_outranks_a_successful_attempt(clock: FakeClock) -> None:
    cancel = Event()

    error = error_from(
        lambda: wait_until(
            lambda: "ready",
            options=WaitOptions(timeout_seconds=math.inf, sleep_seconds=1.0, on_attempt=lambda _attempt: cancel.set()),
            cancel_event=cancel,
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        WaitCancelledError,
    )

    assert_that(error.attempts).is_equal_to(1)
