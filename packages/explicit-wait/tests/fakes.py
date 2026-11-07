import asyncio
import types
from collections.abc import Generator, Sequence
from threading import Event


class FakeClock:
    """Управляемые часы вместе с управляемым сном.

    Время не идёт само: оно двигается только вызовом ``sleep`` или ``advance``. За счёт
    этого тесты бэкоффа и таймаутов детерминированы и выполняются мгновенно.

    Параметр ``overshoot`` моделирует реальность, в которой и ``time.sleep``, и event loop
    гарантируют только нижнюю границу паузы: сон сдвигает часы на запрошенное время плюс
    заданную задержку пробуждения.
    """

    def __init__(self, start: float = 0.0, *, overshoot: float = 0.0) -> None:
        """Инициализировать объект.

        :param start: значение настройки ``start``.
        :param overshoot: значение настройки ``overshoot``.
        """
        self._now = start
        self._overshoot = overshoot
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        """Получить текущее показание часов."""
        return self._now

    def sleep(self, seconds: float) -> None:
        """Проспать заданное время, сдвинув часы вперёд."""
        self.sleeps.append(seconds)
        self._now += seconds + self._overshoot

    async def async_sleep(self, seconds: float) -> None:
        """Проспать заданное время в асинхронном коде, уступив управление event loop."""
        self.sleep(seconds)
        await asyncio.sleep(0)

    def advance(self, seconds: float) -> None:
        """Сдвинуть часы вперёд, не записывая это как сон."""
        self._now += seconds


class ScriptedPredicate:
    """Предикат, отдающий заранее заданные значения по порядку.

    Экземпляр исключения в сценарии означает, что попытка должна завершиться этим
    исключением. Обращение за значением после конца сценария — ошибка теста.
    """

    def __init__(self, results: Sequence[object]) -> None:
        """Инициализировать объект.

        :param results: значение настройки ``results``.
        """
        self._results = list(results)
        self.calls = 0

    def __call__(self) -> object:
        if self.calls >= len(self._results):
            message = f"predicate called {self.calls + 1} times, but only {len(self._results)} scripted"
            raise AssertionError(message)
        result = self._results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


class CountingPredicate:
    """Предикат, становящийся truthy на заданной по счёту попытке."""

    def __init__(self, truthy_on_call: int, *, value: object = True) -> None:
        """Инициализировать объект.

        :param truthy_on_call: значение настройки ``truthy_on_call``.
        :param value: значение настройки ``value``.
        """
        self._truthy_on_call = truthy_on_call
        self._value = value
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        return self._value if self.calls >= self._truthy_on_call else None


class FalsyWithHugeRepr:
    """Falsy-результат с очень длинным repr: нужен, чтобы проверить усечение диагностики."""

    REPR_LENGTH = 5000

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "x" * self.REPR_LENGTH


class FalsyWithBrokenRepr:
    """Falsy-результат, у которого ``__repr__`` падает.

    Нужен, чтобы диагностика ошибки не подменяла собой саму ошибку остановки.
    """

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        message = "repr упал"
        raise RuntimeError(message)


class BrokenStrError(Exception):
    """Ожидаемое исключение, у которого падает приведение к строке."""

    def __str__(self) -> str:
        message = "str упал"
        raise RuntimeError(message)


@types.coroutine
def generator_based_awaitable(value: object) -> Generator[None, None, object]:
    """Создать awaitable старого образца, который не является ``collections.abc.Awaitable``.

    :param value: значение, которое вернёт ожидание.
    :return: awaitable-генератор.
    """
    yield from ()
    return value


class AwaitableWithoutClose:
    """Awaitable-объект без метода ``close``.

    Синхронный агрегат обязан отвергать и такие результаты, хотя закрыть их нечем.
    """

    def __await__(self) -> Generator[None, None, bool]:
        yield from ()
        return True


class AwaitableWithBrokenClose:
    """Awaitable-объект, у которого ``close`` падает.

    Очистка не должна подменять собой ошибку о недопустимом асинхронном предикате.
    """

    def __await__(self) -> Generator[None, None, bool]:
        yield from ()
        return True

    def close(self) -> None:
        """Сломанная очистка."""
        message = "close упал"
        raise RuntimeError(message)


@types.coroutine
def _awaitable_that_refuses_to_close() -> Generator[None, None, bool]:
    try:
        yield
    except GeneratorExit:
        message = "close упал"
        raise RuntimeError(message) from None
    return True


def started_awaitable_that_refuses_to_close() -> Generator[None, None, bool]:
    """Создать уже начатый awaitable, чей ``close`` выбрасывает исключение.

    Закрытие такого объекта не должно подменять ошибку о недопустимом асинхронном предикате.

    :return: приостановленный на yield awaitable-генератор.
    """
    awaitable = _awaitable_that_refuses_to_close()
    awaitable.send(None)
    return awaitable


class EventCancelledOnWait(Event):
    """Событие отмены, которое выставляется ровно в момент ожидания паузы.

    Позволяет проверить отмену во время сна без реальных задержек и гонок.
    """

    def wait(self, timeout: float | None = None) -> bool:
        """Выставить событие и дождаться его.

        :param timeout: максимальное время ожидания.
        :return: True, поскольку событие всегда оказывается выставленным.
        """
        self.set()
        return super().wait(timeout)


class AwaitableTrackingClose:
    """Awaitable-объект, запоминающий, вызывали ли у него ``close``."""

    def __init__(self) -> None:
        """Инициализировать объект."""
        self.close_called = False

    def __await__(self) -> Generator[None, None, bool]:
        yield from ()
        return True

    def close(self) -> None:
        """Запомнить факт вызова очистки."""
        self.close_called = True


class FixedRandom:
    def random(self) -> float:
        return 0.375
