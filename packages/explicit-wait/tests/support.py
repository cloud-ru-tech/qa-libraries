import asyncio
from collections.abc import Callable, Coroutine
from typing import TypeVar

import pytest

E = TypeVar("E", bound=BaseException)


def error_from[E: BaseException](action: Callable[[], object], expected: type[E]) -> E:
    """Run an action and return the exception it raises.

    Lets a test end with one assertion: the exception is checked here,
    and the test body checks one aspect of its contents.

    :param action: action expected to raise an exception.
    :param expected: expected exception type.
    :return: caught exception.
    """
    with pytest.raises(expected) as raised:
        action()
    return raised.value


def async_error_from[E: BaseException](action: Coroutine[None, None, object], expected: type[E]) -> E:
    """Run a coroutine and return the exception it raises.

    :param action: coroutine expected to raise an exception.
    :param expected: expected exception type.
    :return: caught exception.
    """
    with pytest.raises(expected) as raised:
        asyncio.run(action)
    return raised.value
