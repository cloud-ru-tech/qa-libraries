import inspect
import logging
import math
import types
from typing import cast

from .exceptions import InvalidPredicateError, safe_str

logger = logging.getLogger(__name__)


def validate_timeout_seconds(timeout_seconds: float) -> float:
    """Validate the maximum wait time.

    :param timeout_seconds: value to check; ``math.inf`` is allowed.
    :return: the same value.
    :raises TypeError: if the value is not a number.
    :raises ValueError: if the number is not positive.
    """
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int | float):
        message = f"timeout_seconds must be a number, got {type(timeout_seconds).__name__}"
        raise TypeError(
            message,
        )
    if math.isnan(timeout_seconds) or timeout_seconds <= 0:
        message = f"timeout_seconds must be a positive number or math.inf, got {timeout_seconds!r}"
        raise ValueError(
            message,
        )
    return timeout_seconds


def validate_max_attempts(max_attempts: int | None) -> int | None:
    """Validate the attempt count limit.

    :param max_attempts: value to check; None means no limit.
    :return: the same value.
    :raises TypeError: if the value is not an integer.
    :raises ValueError: if the number is not greater than zero.
    """
    if max_attempts is None:
        return None
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        message = f"max_attempts must be a positive integer or None, got {max_attempts!r}"
        raise TypeError(
            message,
        )
    if max_attempts < 1:
        message = f"max_attempts must be a positive integer or None, got {max_attempts!r}"
        raise ValueError(
            message,
        )
    return max_attempts


def reject_awaitable(value: object, *, alternative: str) -> object:
    """Reject an awaitable result from a synchronous predicate.

    An awaitable is always truthy, so accepting it would turn a false condition
    into a success and make an automated test pass incorrectly.

    :param value: synchronous predicate result.
    :param alternative: what to use instead of the synchronous wait.
    :return: the same value if it is not awaitable.
    :raises InvalidPredicateError: if the value is awaitable.
    """
    if not inspect.isawaitable(value):
        return value
    close_quietly(cast("object", value))
    message = (
        "a synchronous predicate must not return an awaitable: it is always truthy "
        f"and would silently pass the check; use {alternative} instead"
    )
    raise InvalidPredicateError(
        message,
    )


def close_quietly(value: object) -> None:
    """Close an unexpected awaitable without letting cleanup replace the final error.

    Only coroutines and generators are closed: their ``close`` is synchronous and predictable.
    A custom ``close`` is not called on arbitrary objects with ``__await__``.

    :param value: awaitable that will not be awaited.
    """
    if not isinstance(value, types.CoroutineType | types.GeneratorType):
        return
    try:
        value.close()
    except Exception as error:
        logger.debug("Не удалось закрыть awaitable-результат предиката: %s", safe_str(error), exc_info=True)
