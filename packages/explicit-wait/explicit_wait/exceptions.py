from __future__ import annotations

import logging
from collections.abc import Callable
from typing import NotRequired, TypedDict, Unpack, cast

MAX_RESULT_REPR_LENGTH = 200

logger = logging.getLogger(__name__)

type ErrorReducer = Callable[[type[WaitError], tuple[object, ...], dict[str, object]], WaitError]
type ErrorState = tuple[type[WaitError], tuple[object, ...], dict[str, object]]


class WaitFailureDetails(TypedDict):
    """Diagnostics for a wait stopped before its condition was satisfied."""

    waiting_for: str
    timeout_seconds: float
    attempts: int
    elapsed_seconds: float
    last_result: NotRequired[object]
    last_exception: NotRequired[Exception | None]


class WaitError(Exception):
    """Base error for the explicit wait library."""

    def __reduce__(self) -> tuple[ErrorReducer, ErrorState]:
        """Restore the entire exception: arguments, fields, and notes.

        The subclass constructor is not called, so custom subclasses with overridden
        signatures and required fields do not prevent deserialization.
        """
        return (
            _rebuild_error,
            (type(self), cast("tuple[object, ...]", self.args), cast("dict[str, object]", self.__dict__).copy()),
        )


class InvalidPredicateError(WaitError, TypeError):
    """The predicate violated the synchronous wait contract.

    Inherits from ``TypeError`` so callers can catch it as usual,
    and from ``WaitError`` so ``expected_exceptions`` cannot swallow it.
    """


class WaitStoppedError(WaitError):
    """The wait stopped before its condition was satisfied.

    Carries the last attempt's diagnostics so a failed automated test explains its own cause.
    """

    def __init__(self, **details: Unpack[WaitFailureDetails]) -> None:
        """Store the last attempt's diagnostics.

        :param details: description of the wait and its last result.
        """
        self.waiting_for = details["waiting_for"]
        self.timeout_seconds = details["timeout_seconds"]
        self.attempts = details["attempts"]
        self.elapsed_seconds = details["elapsed_seconds"]
        self.last_result = details.get("last_result")
        self.last_exception = details.get("last_exception")
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        parts = [
            f"{self._reason()} waiting for {self.waiting_for}",
            f"attempts: {self.attempts}",
            f"elapsed: {self.elapsed_seconds:.3f}s",
        ]
        if self.last_exception is not None:
            parts.append(f"last exception: {type(self.last_exception).__name__}: {safe_str(self.last_exception)}")
        else:
            parts.append(f"last result: {self._last_result_repr()}")
        return f"{parts[0]} ({', '.join(parts[1:])})"

    def _reason(self) -> str:
        return "Wait stopped"

    def _last_result_repr(self) -> str:
        text = safe_repr(self.last_result)
        if len(text) <= MAX_RESULT_REPR_LENGTH:
            return text
        return f"{text[:MAX_RESULT_REPR_LENGTH]}... (truncated)"


class TimeoutExpiredError(WaitStoppedError, TimeoutError):
    """The wait stopped because of its time limit.

    Inherits from built-in ``TimeoutError``, allowing timeouts from this library and
    ``asyncio`` to be caught with one ``except``. Note that ``httpx.TimeoutException``
    is outside this hierarchy and must be caught separately.

    ``deadline_reached`` distinguishes between a deadline that actually passed and
    a next pause that no longer fit, making a new attempt pointless.
    """

    def __init__(self, *, deadline_reached: bool = True, **details: Unpack[WaitFailureDetails]) -> None:
        """Store diagnostics for stopping on the time limit.

        :param deadline_reached: whether the deadline actually passed.
        :param details: description of the wait and its last result.
        """
        self.deadline_reached = deadline_reached
        super().__init__(**details)

    def _reason(self) -> str:
        if self.deadline_reached:
            return f"Timeout of {self.timeout_seconds} seconds expired"
        return f"No further attempt could start before the {self.timeout_seconds} second deadline"


class AttemptsExhaustedError(WaitStoppedError):
    """The maximum number of attempts set by ``max_attempts`` was exhausted."""

    def _reason(self) -> str:
        return f"All {self.attempts} attempts exhausted"


class WaitCancelledError(WaitError):
    """The wait was canceled externally through ``cancel_event``."""

    def __init__(self, *, waiting_for: str, attempts: int, elapsed_seconds: float) -> None:
        """Initialize the object.

        :param waiting_for: Value of ``waiting_for``.
        :param attempts: Value of ``attempts``.
        :param elapsed_seconds: Value of ``elapsed_seconds``.
        """
        self.waiting_for = waiting_for
        self.attempts = attempts
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"Wait for {waiting_for} cancelled (attempts: {attempts}, elapsed: {elapsed_seconds:.3f}s)",
        )


def safe_repr(value: object) -> str:
    """Get a value's repr without replacing the original error.

    :param value: any object whose ``__repr__`` may raise an exception.
    :return: object repr or a failure marker.
    """
    try:
        return repr(value)
    except Exception as error:
        logger.debug("Не удалось получить repr результата", exc_info=True)
        return f"<repr failed: {type(error).__name__}>"


def safe_str(value: object) -> str:
    """Get a string representation without replacing the original error.

    :param value: any object whose ``__str__`` may raise an exception.
    :return: object string representation or a failure marker.
    """
    try:
        return str(value)
    except Exception as error:
        logger.debug("Не удалось получить строку результата", exc_info=True)
        return f"<str failed: {type(error).__name__}>"


def _rebuild_error(
    error_class: type[WaitError],
    args: tuple[object, ...],
    state: dict[str, object],
) -> WaitError:
    error = error_class.__new__(error_class)
    BaseException.__init__(error, *args)
    cast("dict[str, object]", error.__dict__).update(state)
    return error
