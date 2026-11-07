import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Iterable
from typing import cast

from .types import AsyncPredicate, Predicate
from .validators import reject_awaitable


class Aggregate(ABC):
    """Базовый класс для композиции синхронных предикатов.

    Агрегат не хранит результаты проверок между вызовами: каждая проверка запускает
    предикаты заново, поэтому один и тот же агрегат можно использовать в нескольких
    ожиданиях и из нескольких потоков.

    Асинхронные предикаты не принимаются: awaitable-объект всегда truthy, поэтому
    незаметно превратил бы ложное условие в успешное. Для них есть ``AsyncAllOf``
    и ``AsyncAnyOf``.
    """

    def __init__(self, predicates: Iterable[Predicate]) -> None:
        """Инициализировать объект.

        :param predicates: значение настройки ``predicates``.
        """
        self._predicates = tuple(predicates)
        if not self._predicates:
            message = "aggregate requires at least one predicate"
            raise ValueError(message)

    @property
    def predicates(self) -> tuple[Predicate, ...]:
        """Получить предикаты агрегата."""
        return self._predicates

    @abstractmethod
    def __call__(self) -> bool:
        """Проверить составное условие."""

    def __and__(self, other: Predicate) -> "AllOf":
        """Скомбинировать с другим предикатом по «и»."""
        return AllOf([self, other])

    def __or__(self, other: Predicate) -> "AnyOf":
        """Скомбинировать с другим предикатом по «или»."""
        return AnyOf([self, other])

    def check(self, predicate: Predicate) -> object:
        """Вызвать предикат, отвергнув асинхронный результат.

        Собственные синхронные агрегаты обязаны вызывать предикаты только через этот метод:
        awaitable-объект всегда truthy и иначе молча превратил бы ложное условие в успешное.

        :param predicate: предикат агрегата.
        :return: результат предиката.
        :raises InvalidPredicateError: если предикат вернул awaitable.
        """
        return reject_awaitable(predicate(), alternative="AsyncAllOf or AsyncAnyOf")


class AllOf(Aggregate):
    """Истинно, когда все предикаты истинны одновременно.

    Предикаты вызываются в порядке перечисления и вычисляются по короткой схеме:
    первый ложный предикат прекращает проверку.
    """

    def __call__(self) -> bool:
        """Проверить, что все предикаты истинны."""
        return all(self.check(predicate) for predicate in self._predicates)


class AnyOf(Aggregate):
    """Истинно, когда истинен хотя бы один предикат.

    Предикаты вызываются в порядке перечисления и вычисляются по короткой схеме:
    первый истинный предикат прекращает проверку.
    """

    def __call__(self) -> bool:
        """Проверить, что истинен хотя бы один предикат."""
        return any(self.check(predicate) for predicate in self._predicates)


class AsyncAggregate(ABC):
    """Базовый класс для композиции асинхронных предикатов.

    Принимает как корутинные, так и обычные функции. Состояние между вызовами не хранится.
    """

    def __init__(self, predicates: Iterable[AsyncPredicate]) -> None:
        """Инициализировать объект.

        :param predicates: значение настройки ``predicates``.
        """
        self._predicates = tuple(predicates)
        if not self._predicates:
            message = "aggregate requires at least one predicate"
            raise ValueError(message)

    @property
    def predicates(self) -> tuple[AsyncPredicate, ...]:
        """Получить предикаты агрегата."""
        return self._predicates

    @abstractmethod
    async def __call__(self) -> bool:
        """Проверить составное условие."""

    def __and__(self, other: AsyncPredicate) -> "AsyncAllOf":
        """Скомбинировать с другим предикатом по «и»."""
        return AsyncAllOf([self, other])

    def __or__(self, other: AsyncPredicate) -> "AsyncAnyOf":
        """Скомбинировать с другим предикатом по «или»."""
        return AsyncAnyOf([self, other])

    async def check(self, predicate: AsyncPredicate) -> object:
        """Вызвать предикат и дождаться его, если он асинхронный.

        :param predicate: предикат агрегата.
        :return: результат предиката.
        """
        result = predicate()
        if inspect.isawaitable(result):
            return await cast("Awaitable[object]", result)
        return result


class AsyncAllOf(AsyncAggregate):
    """Истинно, когда все асинхронные предикаты истинны одновременно.

    Предикаты выполняются последовательно и по короткой схеме: первый ложный предикат
    прекращает проверку, остальные не вызываются.
    """

    async def __call__(self) -> bool:
        """Проверить, что все предикаты истинны."""
        for predicate in self._predicates:
            if not await self.check(predicate):
                return False
        return True


class AsyncAnyOf(AsyncAggregate):
    """Истинно, когда истинен хотя бы один асинхронный предикат.

    Предикаты выполняются последовательно и по короткой схеме: первый истинный предикат
    прекращает проверку.
    """

    async def __call__(self) -> bool:
        """Проверить, что истинен хотя бы один предикат."""
        for predicate in self._predicates:
            if await self.check(predicate):
                return True
        return False
