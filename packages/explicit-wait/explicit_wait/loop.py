import logging
import time
from collections.abc import Callable
from typing import TypeVar, cast

from .attempt import Attempt
from .backoff import Backoff
from .config import WaitOptions, get_config
from .deadline import Deadline
from .exceptions import AttemptsExhaustedError, TimeoutExpiredError, WaitStoppedError, safe_repr, safe_str
from .types import UNSET, Clock
from .validators import validate_max_attempts

logger = logging.getLogger(__name__)

STOP_ON_TIMEOUT = "timeout"
STOP_ON_NO_TIME = "no_time_for_next_attempt"
STOP_ON_ATTEMPTS = "attempts"

SuccessCheck = Callable[[object], bool]

T = TypeVar("T")


def describe_predicate(predicate: object, message: str | None) -> str:
    """Build a readable description of the expected condition.

    Object addresses and argument repr are intentionally omitted: addresses are useless in reports,
    and repr may expose sensitive data in logs.

    :param predicate: predicate function or another callable object.
    :param message: user-defined description; takes precedence.
    :return: description for the error message.
    """
    if message is not None:
        return message
    name = cast("object", getattr(predicate, "__qualname__", None)) or cast(
        "object", getattr(predicate, "__name__", None)
    )
    if isinstance(name, str) and name:
        return name
    return type(predicate).__name__


class WaitLoop[T]:
    """Wait core without I/O.

    Stores wait state and decides what to do next without performing actions itself:
    the driver calls the predicate and sleeps. This lets synchronous and asynchronous
    waits share stopping, backoff, and diagnostic logic.

    Stopping reasons are checked in a fixed order: an elapsed deadline first,
    then exhausted attempts, then a next pause that cannot fit before the deadline.
    """

    def __init__(
        self,
        *,
        waiting_for: str,
        options: WaitOptions,
        succeeds_on: SuccessCheck = bool,
        clock: Clock = time.monotonic,
    ) -> None:
        """Initialize the object.

        :param waiting_for: Value of ``waiting_for``.
        :param options: parameters for one wait.
        :param succeeds_on: Value of ``succeeds_on``.
        :param clock: Value of ``clock``.
        """
        config = get_config()
        self._waiting_for = waiting_for
        timeout = config.timeout_seconds if options.timeout_seconds is None else options.timeout_seconds
        backoff = config.backoff if options.sleep_seconds is None else Backoff.parse(options.sleep_seconds)
        maximum = config.max_attempts if options.max_attempts is UNSET else options.max_attempts
        self._deadline = Deadline(timeout, clock=clock)
        self._delays = backoff.delays()
        self._max_attempts = validate_max_attempts(maximum)
        self._expected_exceptions = options.expected_exceptions
        self._retry_on_exception = options.retry_on_exception
        self._succeeds_on = succeeds_on
        self._attempts = 0
        self._is_satisfied = False
        self._last_result: T | None = None
        self._last_exception: Exception | None = None
        self._stop_reason = STOP_ON_TIMEOUT

    @property
    def waiting_for(self) -> str:
        """Get a description of the expected condition."""
        return self._waiting_for

    @property
    def attempts(self) -> int:
        """Get the number of completed attempts."""
        return self._attempts

    @property
    def is_satisfied(self) -> bool:
        """Check that the wait condition is satisfied."""
        return self._is_satisfied

    @property
    def stopped_on_attempts(self) -> bool:
        """Check that the wait stopped because attempts were exhausted, rather than time."""
        return self._stop_reason == STOP_ON_ATTEMPTS

    @property
    def value(self) -> T:
        """Get the result that satisfied the wait.

        Meaningful only when ``is_satisfied`` is true and a truthy result counts as success.
        """
        # A truthy result excludes None, but types cannot express a truthy T.
        return cast("T", self._last_result)

    def elapsed_seconds(self) -> float:
        """Get the time elapsed since the wait started, in seconds."""
        return self._deadline.elapsed_seconds()

    def expire_if_deadline_reached(self) -> bool:
        """Check the deadline before starting the next attempt.

        Called after sleeping, as wakeup may happen later than requested: both ``time.sleep``
        and the event loop guarantee only a minimum pause.

        :return: True if another attempt can no longer start.
        """
        if self._deadline.seconds_remaining() > 0:
            return False
        self._stop_reason = STOP_ON_TIMEOUT
        return True

    def start_attempt(self) -> None:
        """Mark the start of the next attempt."""
        self._attempts += 1

    def is_expected(self, error: Exception) -> bool:
        """Check whether to ignore a predicate exception and retry.

        :param error: exception raised by the predicate.
        :return: True if the attempt should be retried.
        """
        if not isinstance(error, self._expected_exceptions):
            return False
        if self._retry_on_exception is None:
            return True
        return self._retry_on_exception(error)

    def record_result(self, value: T | None) -> None:
        """Store the attempt result.

        :param value: value returned by the predicate.
        """
        self._last_result = value
        self._last_exception = None
        self._is_satisfied = self._succeeds_on(value)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Ожидание %s: попытка %d вернула %s",
                self._waiting_for,
                self._attempts,
                safe_repr(value),
            )

    def record_exception(self, error: Exception) -> None:
        """Store the attempt's expected exception.

        :param error: exception raised by the predicate.
        """
        self._last_result = None
        self._last_exception = error
        self._is_satisfied = False
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Ожидание %s: попытка %d завершилась ожидаемым %s: %s",
                self._waiting_for,
                self._attempts,
                type(error).__name__,
                safe_str(error),
            )

    def next_delay(self) -> float | None:
        """Calculate the pause before the next attempt.

        :return: pause in seconds, or None if the wait should stop.
        """
        remaining = self._deadline.seconds_remaining()
        if remaining <= 0:
            self._stop_reason = STOP_ON_TIMEOUT
            return None
        if self._max_attempts is not None and self._attempts >= self._max_attempts:
            self._stop_reason = STOP_ON_ATTEMPTS
            return None
        delay = next(self._delays)
        if delay >= remaining:
            self._stop_reason = STOP_ON_NO_TIME
            return None
        return delay

    def build_attempt(self, *, next_sleep_seconds: float | None) -> Attempt:
        """Build the last attempt's description for a hook.

        :param next_sleep_seconds: pause before the next attempt, or None if none is planned.
        :return: attempt description.
        """
        return self._attempt_at(self._deadline.elapsed_seconds(), next_sleep_seconds)

    def terminal_snapshot(self) -> tuple[WaitStoppedError, Attempt]:
        """Build a consistent stopping error and last attempt description.

        The clock is read once, so both objects describe exactly the same moment.

        :return: pair of the stopping error and last attempt description.
        """
        elapsed = self._deadline.elapsed_seconds()
        if elapsed >= self._deadline.timeout_seconds:
            self._stop_reason = STOP_ON_TIMEOUT
        return self._stop_error_at(elapsed), self._attempt_at(elapsed, None)

    def _attempt_at(self, elapsed_seconds: float, next_sleep_seconds: float | None) -> Attempt:
        return Attempt(
            number=self._attempts,
            elapsed_seconds=elapsed_seconds,
            result=self._last_result,
            exception=self._last_exception,
            next_sleep_seconds=next_sleep_seconds,
        )

    def _stop_error_at(self, elapsed_seconds: float) -> WaitStoppedError:
        if self._stop_reason == STOP_ON_ATTEMPTS:
            return AttemptsExhaustedError(
                waiting_for=self._waiting_for,
                timeout_seconds=self._deadline.timeout_seconds,
                attempts=self._attempts,
                elapsed_seconds=elapsed_seconds,
                last_result=self._last_result,
                last_exception=self._last_exception,
            )
        return TimeoutExpiredError(
            waiting_for=self._waiting_for,
            timeout_seconds=self._deadline.timeout_seconds,
            attempts=self._attempts,
            elapsed_seconds=elapsed_seconds,
            last_result=self._last_result,
            last_exception=self._last_exception,
            deadline_reached=self._stop_reason == STOP_ON_TIMEOUT,
        )
