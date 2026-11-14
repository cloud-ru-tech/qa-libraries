import asyncio
import types
from collections.abc import Generator, Sequence
from threading import Event


class FakeClock:
    """Controlled clock with controlled sleep.

    Time does not pass on its own: only ``sleep`` or ``advance`` move it forward. This makes
    backoff and timeout tests deterministic and immediate.

    ``overshoot`` models how both ``time.sleep`` and the event loop guarantee only
    a minimum pause: sleep advances the clock by the requested time plus
    the specified wakeup delay.
    """

    def __init__(self, start: float = 0.0, *, overshoot: float = 0.0) -> None:
        """Initialize the object.

        :param start: Value of ``start``.
        :param overshoot: Value of ``overshoot``.
        """
        self._now = start
        self._overshoot = overshoot
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        """Get the current clock reading."""
        return self._now

    def sleep(self, seconds: float) -> None:
        """Sleep for the given duration by advancing the clock."""
        self.sleeps.append(seconds)
        self._now += seconds + self._overshoot

    async def async_sleep(self, seconds: float) -> None:
        """Sleep in asynchronous code, yielding control to the event loop."""
        self.sleep(seconds)
        await asyncio.sleep(0)

    def advance(self, seconds: float) -> None:
        """Advance the clock without recording a sleep."""
        self._now += seconds


class ScriptedPredicate:
    """Predicate returning predefined values in order.

    An exception instance in the script makes the attempt raise that
    exception. Requesting a value after the script ends is a test error.
    """

    def __init__(self, results: Sequence[object]) -> None:
        """Initialize the object.

        :param results: Value of ``results``.
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
    """Predicate that becomes truthy on a specified attempt."""

    def __init__(self, truthy_on_call: int, *, value: object = True) -> None:
        """Initialize the object.

        :param truthy_on_call: Value of ``truthy_on_call``.
        :param value: Value of ``value``.
        """
        self._truthy_on_call = truthy_on_call
        self._value = value
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        return self._value if self.calls >= self._truthy_on_call else None


class FalsyWithHugeRepr:
    """Falsy result with a very long repr for testing diagnostic truncation."""

    REPR_LENGTH = 5000

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "x" * self.REPR_LENGTH


class FalsyWithBrokenRepr:
    """Falsy result whose ``__repr__`` raises an exception.

    Ensures error diagnostics do not replace the stopping error itself.
    """

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        message = "repr упал"
        raise RuntimeError(message)


class BrokenStrError(Exception):
    """Expected exception whose string conversion raises an error."""

    def __str__(self) -> str:
        message = "str упал"
        raise RuntimeError(message)


@types.coroutine
def generator_based_awaitable(value: object) -> Generator[None, None, object]:
    """Create a legacy awaitable that is not a ``collections.abc.Awaitable``.

    :param value: value returned by the awaitable.
    :return: awaitable generator.
    """
    yield from ()
    return value


class AwaitableWithoutClose:
    """Awaitable without a ``close`` method.

    Synchronous combinations must reject these results even though they cannot close them.
    """

    def __await__(self) -> Generator[None, None, bool]:
        yield from ()
        return True


class AwaitableWithBrokenClose:
    """Awaitable whose ``close`` raises an exception.

    Cleanup must not replace the error about an invalid asynchronous predicate.
    """

    def __await__(self) -> Generator[None, None, bool]:
        yield from ()
        return True

    def close(self) -> None:
        """Fail during cleanup."""
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
    """Create an already started awaitable whose ``close`` raises an exception.

    Closing this object must not replace the error about an invalid asynchronous predicate.

    :return: awaitable generator suspended at yield.
    """
    awaitable = _awaitable_that_refuses_to_close()
    awaitable.send(None)
    return awaitable


class EventCancelledOnWait(Event):
    """Cancellation event set exactly when waiting for a pause.

    Tests cancellation during sleep without real delays or races.
    """

    def wait(self, timeout: float | None = None) -> bool:
        """Set the event and wait for it.

        :param timeout: maximum wait time.
        :return: True, as the event is always set.
        """
        self.set()
        return super().wait(timeout)


class AwaitableTrackingClose:
    """Awaitable that records whether its ``close`` was called."""

    def __init__(self) -> None:
        """Initialize the object."""
        self.close_called = False

    def __await__(self) -> Generator[None, None, bool]:
        yield from ()
        return True

    def close(self) -> None:
        """Record the cleanup call."""
        self.close_called = True


class FixedRandom:
    def random(self) -> float:
        return 0.375
