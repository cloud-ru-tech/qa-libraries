import time

from .types import Clock
from .validators import validate_timeout_seconds


class Deadline:
    """Wait deadline measured with a monotonic clock.

    Unlike ``time.time``, monotonic clocks do not shift on NTP synchronization
    or manual system time changes, keeping wait durations predictable.
    """

    def __init__(self, timeout_seconds: float, *, clock: Clock = time.monotonic) -> None:
        """Initialize the object.

        :param timeout_seconds: Value of ``timeout_seconds``.
        :param clock: Value of ``clock``.
        """
        self._timeout_seconds = validate_timeout_seconds(timeout_seconds)
        self._clock = clock
        self._started_at = clock()

    @property
    def timeout_seconds(self) -> float:
        """Get the configured maximum wait time in seconds."""
        return self._timeout_seconds

    def elapsed_seconds(self) -> float:
        """Get the time elapsed since deadline creation, in seconds."""
        return self._clock() - self._started_at

    def seconds_remaining(self) -> float:
        """Get the time remaining before the deadline, in seconds, with a minimum of zero."""
        return max(0.0, self._timeout_seconds - self.elapsed_seconds())
