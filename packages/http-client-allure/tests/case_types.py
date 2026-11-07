from collections.abc import Callable
from typing import Protocol, cast

from pytest_cases import parametrize_with_cases


class CaseDecorator(Protocol):
    def __call__[**P, R](self, function: Callable[P, R]) -> Callable[P, R]: ...


class CaseParametrizer(Protocol):
    def __call__(self, argnames: str) -> CaseDecorator: ...


parameterize_cases = cast("CaseParametrizer", parametrize_with_cases)
