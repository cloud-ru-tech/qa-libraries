from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attempt:
    """Result of one wait attempt, passed to hooks.

    Exactly one of ``result`` and ``exception`` is meaningful: if the predicate raises
    an exception from ``expected_exceptions``, ``exception`` is set and ``result`` is None.
    """

    number: int
    elapsed_seconds: float
    result: object = None
    exception: Exception | None = None
    next_sleep_seconds: float | None = None

    @property
    def has_no_planned_sleep(self) -> bool:
        """Check that no next pause is planned at the time of the decision.

        This is a snapshot of the plan, not a guarantee of finality: an attempt can be last even
        with a planned pause if the wait is canceled externally, wakes up later than requested,
        or the hook itself uses up the remaining time.
        """
        return self.next_sleep_seconds is None
