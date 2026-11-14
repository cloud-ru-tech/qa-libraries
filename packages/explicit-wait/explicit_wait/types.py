from collections.abc import Awaitable, Callable
from enum import Enum, auto
from typing import Literal

Clock = Callable[[], float]
Sleeper = Callable[[float], None]
AsyncSleeper = Callable[[float], Awaitable[None]]
ExceptionsType = type[Exception] | tuple[type[Exception], ...]
ExceptionFilter = Callable[[Exception], bool]
Predicate = Callable[[], object]
AsyncPredicate = Callable[[], object | Awaitable[object]]


class Unset(Enum):
    """Marker for an omitted argument.

    Used where None is meaningful and cannot serve as a marker
    for an omitted argument.
    """

    TOKEN = auto()


UNSET = Unset.TOKEN

MaxAttempts = int | None | Literal[Unset.TOKEN]
