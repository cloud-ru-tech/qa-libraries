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
    """Маркер «аргумент не передан».

    Нужен там, где None — осмысленное значение и его нельзя использовать как признак
    отсутствия аргумента.
    """

    TOKEN = auto()


UNSET = Unset.TOKEN

MaxAttempts = int | None | Literal[Unset.TOKEN]
