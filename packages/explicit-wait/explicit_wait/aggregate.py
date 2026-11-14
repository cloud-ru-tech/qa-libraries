import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Iterable
from typing import cast

from .types import AsyncPredicate, Predicate
from .validators import reject_awaitable


class Aggregate(ABC):
    """Base class for combining synchronous predicates.

    Combinations do not store check results between calls: each check reruns
    the predicates, so the same combination can be reused across waits
    and threads.

    Asynchronous predicates are rejected: an awaitable is always truthy and
    would silently turn a false condition into a success. Use ``AsyncAllOf``
    and ``AsyncAnyOf`` for them.
    """

    def __init__(self, predicates: Iterable[Predicate]) -> None:
        """Initialize the object.

        :param predicates: Value of ``predicates``.
        """
        self._predicates = tuple(predicates)
        if not self._predicates:
            message = "aggregate requires at least one predicate"
            raise ValueError(message)

    @property
    def predicates(self) -> tuple[Predicate, ...]:
        """Get the combination's predicates."""
        return self._predicates

    @abstractmethod
    def __call__(self) -> bool:
        """Check the combined condition."""

    def __and__(self, other: Predicate) -> "AllOf":
        """Combine with another predicate using AND."""
        return AllOf([self, other])

    def __or__(self, other: Predicate) -> "AnyOf":
        """Combine with another predicate using OR."""
        return AnyOf([self, other])

    def check(self, predicate: Predicate) -> object:
        """Call a predicate and reject asynchronous results.

        Custom synchronous combinations must call predicates only through this method:
        an awaitable is always truthy and would silently turn a false condition into a success.

        :param predicate: predicate in the combination.
        :return: predicate result.
        :raises InvalidPredicateError: if the predicate returns an awaitable.
        """
        return reject_awaitable(predicate(), alternative="AsyncAllOf or AsyncAnyOf")


class AllOf(Aggregate):
    """True when all predicates are true at once.

    Predicates run in the listed order with short-circuit evaluation:
    the first false predicate stops the check.
    """

    def __call__(self) -> bool:
        """Check that all predicates are true."""
        return all(self.check(predicate) for predicate in self._predicates)


class AnyOf(Aggregate):
    """True when at least one predicate is true.

    Predicates run in the listed order with short-circuit evaluation:
    the first true predicate stops the check.
    """

    def __call__(self) -> bool:
        """Check that at least one predicate is true."""
        return any(self.check(predicate) for predicate in self._predicates)


class AsyncAggregate(ABC):
    """Base class for combining asynchronous predicates.

    Accepts coroutine and regular functions. No state is stored between calls.
    """

    def __init__(self, predicates: Iterable[AsyncPredicate]) -> None:
        """Initialize the object.

        :param predicates: Value of ``predicates``.
        """
        self._predicates = tuple(predicates)
        if not self._predicates:
            message = "aggregate requires at least one predicate"
            raise ValueError(message)

    @property
    def predicates(self) -> tuple[AsyncPredicate, ...]:
        """Get the combination's predicates."""
        return self._predicates

    @abstractmethod
    async def __call__(self) -> bool:
        """Check the combined condition."""

    def __and__(self, other: AsyncPredicate) -> "AsyncAllOf":
        """Combine with another predicate using AND."""
        return AsyncAllOf([self, other])

    def __or__(self, other: AsyncPredicate) -> "AsyncAnyOf":
        """Combine with another predicate using OR."""
        return AsyncAnyOf([self, other])

    async def check(self, predicate: AsyncPredicate) -> object:
        """Call a predicate and await it if asynchronous.

        :param predicate: predicate in the combination.
        :return: predicate result.
        """
        result = predicate()
        if inspect.isawaitable(result):
            return await cast("Awaitable[object]", result)
        return result


class AsyncAllOf(AsyncAggregate):
    """True when all asynchronous predicates are true at once.

    Predicates run sequentially with short-circuit evaluation: the first false predicate
    stops the check, and the remaining predicates are not called.
    """

    async def __call__(self) -> bool:
        """Check that all predicates are true."""
        for predicate in self._predicates:
            if not await self.check(predicate):
                return False
        return True


class AsyncAnyOf(AsyncAggregate):
    """True when at least one asynchronous predicate is true.

    Predicates run sequentially with short-circuit evaluation: the first true predicate
    stops the check.
    """

    async def __call__(self) -> bool:
        """Check that at least one predicate is true."""
        for predicate in self._predicates:
            if await self.check(predicate):
                return True
        return False
