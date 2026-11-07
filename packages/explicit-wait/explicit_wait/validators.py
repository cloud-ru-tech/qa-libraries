import inspect
import logging
import math
import types
from typing import cast

from .exceptions import InvalidPredicateError, safe_str

logger = logging.getLogger(__name__)


def validate_timeout_seconds(timeout_seconds: float) -> float:
    """Проверить максимальное время ожидания.

    :param timeout_seconds: проверяемое значение; ``math.inf`` допустим.
    :return: то же значение.
    :raises TypeError: если передано не число.
    :raises ValueError: если число не является положительным.
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
    """Проверить ограничение по числу попыток.

    :param max_attempts: проверяемое значение; None означает отсутствие ограничения.
    :return: то же значение.
    :raises TypeError: если передано не целое число.
    :raises ValueError: если число не больше нуля.
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
    """Отвергнуть awaitable-результат синхронного предиката.

    Awaitable-объект всегда truthy, поэтому незамеченным он превратил бы ложное условие
    в успешное и дал бы ложно проходящий автотест.

    :param value: результат синхронного предиката.
    :param alternative: что использовать вместо синхронного ожидания.
    :return: то же значение, если оно не awaitable.
    :raises InvalidPredicateError: если значение является awaitable.
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
    """Закрыть неожиданный awaitable, не позволяя очистке подменить итоговую ошибку.

    Закрываются только корутины и генераторы: у них ``close`` синхронный и предсказуемый.
    Для произвольного объекта с ``__await__`` пользовательский ``close`` не вызывается.

    :param value: awaitable-объект, который не будет ожидаться.
    """
    if not isinstance(value, types.CoroutineType | types.GeneratorType):
        return
    try:
        value.close()
    except Exception as error:
        logger.debug("Не удалось закрыть awaitable-результат предиката: %s", safe_str(error), exc_info=True)
