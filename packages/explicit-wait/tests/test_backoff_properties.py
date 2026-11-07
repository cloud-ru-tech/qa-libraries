import math
from itertools import islice
from typing import Protocol, cast

from explicit_wait import Backoff
from hypothesis import given
from hypothesis import strategies as st

from .matchers import assert_that

SEQUENCE_LENGTH = 30

positive_intervals = st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False)
multipliers = st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False)
jitters = st.floats(min_value=0.0, max_value=0.999, allow_nan=False, allow_infinity=False)


class _PropertyDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


@cast("_PropertyDecorator", given(initial=positive_intervals, multiplier=multipliers, jitter=jitters))
def test_every_delay_is_positive(initial: float, multiplier: float, jitter: float) -> None:
    strategy = Backoff(initial_seconds=initial, multiplier=multiplier, jitter=jitter)

    delays = list(islice(strategy.delays(), SEQUENCE_LENGTH))

    assert_that([delay for delay in delays if delay <= 0]).is_empty()


@cast("_PropertyDecorator", given(initial=positive_intervals, multiplier=multipliers))
def test_delays_never_decrease_without_jitter(initial: float, multiplier: float) -> None:
    strategy = Backoff(initial_seconds=initial, multiplier=multiplier)

    delays = list(islice(strategy.delays(), SEQUENCE_LENGTH))

    assert_that(delays).is_equal_to(sorted(delays))


@cast(
    "_PropertyDecorator",
    given(initial=positive_intervals, cap_factor=st.floats(min_value=1.0, max_value=1000.0), multiplier=multipliers),
)
def test_delays_never_exceed_the_maximum(initial: float, cap_factor: float, multiplier: float) -> None:
    maximum = initial * cap_factor
    strategy = Backoff(initial_seconds=initial, maximum_seconds=maximum, multiplier=multiplier)

    delays = list(islice(strategy.delays(), SEQUENCE_LENGTH))

    assert_that([delay for delay in delays if delay > maximum]).is_empty()


@cast("_PropertyDecorator", given(initial=positive_intervals, jitter=st.floats(min_value=0.01, max_value=0.999)))
def test_jitter_keeps_delays_within_the_planned_share(initial: float, jitter: float) -> None:
    strategy = Backoff(initial_seconds=initial, jitter=jitter)

    delays = list(islice(strategy.delays(), SEQUENCE_LENGTH))

    assert_that([delay for delay in delays if not initial * (1 - jitter) <= delay <= initial]).is_empty()


@cast("_PropertyDecorator", given(initial=positive_intervals, multiplier=multipliers, jitter=jitters))
def test_every_delay_is_finite(initial: float, multiplier: float, jitter: float) -> None:
    strategy = Backoff(
        initial_seconds=initial,
        maximum_seconds=initial * 1000,
        multiplier=multiplier,
        jitter=jitter,
    )

    delays = list(islice(strategy.delays(), SEQUENCE_LENGTH))

    assert_that([delay for delay in delays if not math.isfinite(delay)]).is_empty()
