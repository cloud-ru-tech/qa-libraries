import copy
import pickle
from io import BytesIO
from typing import cast

import pytest
from explicit_wait import (
    AttemptsExhaustedError,
    TimeoutExpiredError,
    WaitCancelledError,
    WaitError,
    WaitStoppedError,
)

from .matchers import assert_that


class _TicketedTimeoutError(TimeoutExpiredError):
    def __init__(
        self,
        *,
        code: str,
        waiting_for: str,
        timeout_seconds: float,
        attempts: int,
        elapsed_seconds: float,
    ) -> None:
        """Initialize the object.

        :param code: Value of ``code``.
        :param waiting_for: Value of ``waiting_for``.
        :param timeout_seconds: Value of ``timeout_seconds``.
        :param attempts: Value of ``attempts``.
        :param elapsed_seconds: Value of ``elapsed_seconds``.
        """
        self.code = code
        super().__init__(
            waiting_for=waiting_for,
            timeout_seconds=timeout_seconds,
            attempts=attempts,
            elapsed_seconds=elapsed_seconds,
        )


class _ExceptionUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> object:
        rebuild = WaitError("probe").__reduce__()[0]
        allowed = (
            TimeoutExpiredError,
            AttemptsExhaustedError,
            WaitCancelledError,
            WaitStoppedError,
            _TicketedTimeoutError,
            ValueError,
            rebuild,
        )
        for candidate in allowed:
            if (candidate.__module__, candidate.__name__) == (module, name):
                return candidate
        message = f"Unexpected pickle global: {module}.{name}"
        raise pickle.UnpicklingError(message)


def _round_trip[E: WaitError](error: E) -> E:
    with BytesIO(pickle.dumps(error)) as stream:
        return cast("E", _ExceptionUnpickler(stream).load())


def _timeout_error() -> TimeoutExpiredError:
    return TimeoutExpiredError(
        waiting_for="заказ станет ready",
        timeout_seconds=30.0,
        attempts=4,
        elapsed_seconds=14.0,
        last_result=[1, 2],
        last_exception=ValueError("сервис ответил 500"),
        deadline_reached=False,
    )


def test_timeout_error_survives_a_round_trip() -> None:
    restored = _round_trip(_timeout_error())

    assert_that(str(restored)).is_equal_to(str(_timeout_error()))


def test_timeout_error_keeps_the_deadline_flag() -> None:
    restored = _round_trip(_timeout_error())

    assert_that(restored.deadline_reached).is_false()


def test_timeout_error_keeps_the_last_result() -> None:
    restored = _round_trip(_timeout_error())

    assert_that(restored.last_result).is_equal_to([1, 2])


def test_attempts_exhausted_error_survives_a_round_trip() -> None:
    error = AttemptsExhaustedError(
        waiting_for="реплика догонит",
        timeout_seconds=60.0,
        attempts=7,
        elapsed_seconds=12.5,
    )

    restored = _round_trip(error)

    assert_that(restored.attempts).is_equal_to(7)


def test_cancelled_error_survives_a_round_trip() -> None:
    error = WaitCancelledError(waiting_for="очередь опустеет", attempts=3, elapsed_seconds=1.25)

    restored = _round_trip(error)

    assert_that(restored.elapsed_seconds).is_equal_to(1.25)


@pytest.mark.parametrize(
    "error_class",
    [WaitStoppedError, TimeoutExpiredError, AttemptsExhaustedError],
)
def test_restored_error_keeps_its_class(error_class: type[WaitStoppedError]) -> None:
    error = error_class(waiting_for="условие", timeout_seconds=5.0, attempts=1, elapsed_seconds=0.5)

    restored = _round_trip(error)

    assert_that(type(restored)).is_equal_to(error_class)


def test_notes_survive_a_round_trip() -> None:
    error = _timeout_error()
    error.add_note("сервис был перезапущен")

    restored = _round_trip(error)

    assert_that(restored.__notes__).is_equal_to(["сервис был перезапущен"])


def test_extra_attributes_survive_a_round_trip() -> None:
    error = _timeout_error()
    attribute = "ticket"
    setattr(error, attribute, "QA-42")

    restored = _round_trip(error)

    assert_that(cast("object", getattr(restored, attribute))).is_equal_to("QA-42")


def test_deep_copy_keeps_extra_attributes() -> None:
    error = _timeout_error()
    attribute = "ticket"
    setattr(error, attribute, "QA-7")

    assert_that(cast("object", getattr(copy.deepcopy(error), attribute))).is_equal_to("QA-7")


def test_subclass_with_required_state_survives_a_round_trip() -> None:
    error = _TicketedTimeoutError(
        code="E17",
        waiting_for="счёт выставится",
        timeout_seconds=10.0,
        attempts=2,
        elapsed_seconds=4.0,
    )

    restored = _round_trip(error)

    assert_that(restored.code).is_equal_to("E17")
