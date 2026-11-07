import asyncio
from collections.abc import Callable, Coroutine
from typing import TypeVar

import pytest

E = TypeVar("E", bound=BaseException)


def error_from[E: BaseException](action: Callable[[], object], expected: type[E]) -> E:
    """Выполнить действие и вернуть исключение, которое оно выбросило.

    Позволяет тесту закончиться единственной проверкой: сам факт исключения проверяется
    здесь, а тело теста утверждает что-то одно о его содержимом.

    :param action: действие, которое должно завершиться исключением.
    :param expected: ожидаемый тип исключения.
    :return: перехваченное исключение.
    """
    with pytest.raises(expected) as raised:
        action()
    return raised.value


def async_error_from[E: BaseException](action: Coroutine[None, None, object], expected: type[E]) -> E:
    """Выполнить корутину и вернуть исключение, которое она выбросила.

    :param action: корутина, которая должна завершиться исключением.
    :param expected: ожидаемый тип исключения.
    :return: перехваченное исключение.
    """
    with pytest.raises(expected) as raised:
        asyncio.run(action)
    return raised.value
