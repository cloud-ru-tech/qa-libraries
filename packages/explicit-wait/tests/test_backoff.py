import math
from itertools import islice
from typing import TYPE_CHECKING, cast

import pytest
from explicit_wait import Backoff

from .fakes import FixedRandom
from .matchers import assert_that

if TYPE_CHECKING:
    from explicit_wait.backoff import SleepSecondsType


def test_scalar_gives_a_constant_interval() -> None:
    assert_that(Backoff.parse(1.5)).yields_delays([1.5, 1.5, 1.5, 1.5])


def test_pair_doubles_the_interval() -> None:
    assert_that(Backoff.parse((1.0, 100.0))).yields_delays([1.0, 2.0, 4.0, 8.0, 16.0])


def test_pair_stops_growing_at_the_maximum() -> None:
    assert_that(Backoff.parse((1.0, 10.0))).yields_delays([1.0, 2.0, 4.0, 8.0, 10.0, 10.0])


def test_triple_uses_the_given_multiplier() -> None:
    assert_that(Backoff.parse((1.0, 100.0, 3.0))).yields_delays([1.0, 3.0, 9.0, 27.0, 81.0, 100.0])


def test_missing_maximum_lets_the_interval_grow_without_bound() -> None:
    assert_that(Backoff.parse((2.0, None))).yields_delays([2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0])


def test_multiplier_of_one_keeps_the_interval_constant() -> None:
    assert_that(Backoff.parse((5.0, 90.0, 1.0))).yields_delays([5.0, 5.0, 5.0])


def test_ready_made_strategy_passes_through() -> None:
    strategy = Backoff(initial_seconds=0.25, maximum_seconds=1.0, multiplier=2.0)

    assert_that(Backoff.parse(strategy)).is_same_as(strategy)


def test_jitter_never_exceeds_the_planned_delay() -> None:
    assert_that(Backoff(initial_seconds=4.0, jitter=0.25)).yields_delays_between(3.0, 4.0, count=50)


def test_jitter_is_reproducible_for_a_given_source() -> None:
    strategy = Backoff(initial_seconds=8.0, jitter=0.5)
    expected = list(islice(strategy.delays(FixedRandom()), 5))

    assert_that(strategy).yields_delays(expected, rng=FixedRandom())


def test_rejects_zero_initial_interval() -> None:
    with pytest.raises(ValueError, match="initial_seconds"):
        Backoff(initial_seconds=0.0)


def test_rejects_negative_initial_interval() -> None:
    with pytest.raises(ValueError, match="initial_seconds"):
        Backoff(initial_seconds=-3.0)


def test_rejects_infinite_initial_interval() -> None:
    with pytest.raises(ValueError, match="initial_seconds"):
        Backoff(initial_seconds=math.inf)


def test_rejects_not_a_number_initial_interval() -> None:
    with pytest.raises(ValueError, match="initial_seconds"):
        Backoff(initial_seconds=math.nan)


def test_rejects_maximum_below_initial() -> None:
    with pytest.raises(ValueError, match="maximum_seconds"):
        Backoff(initial_seconds=10.0, maximum_seconds=1.0)


def test_rejects_infinite_maximum() -> None:
    with pytest.raises(ValueError, match="maximum_seconds"):
        Backoff(initial_seconds=1.0, maximum_seconds=math.inf)


def test_rejects_multiplier_below_one() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        Backoff(initial_seconds=10.0, maximum_seconds=20.0, multiplier=0.5)


def test_rejects_negative_multiplier() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        Backoff(initial_seconds=10.0, maximum_seconds=20.0, multiplier=-2.0)


def test_rejects_jitter_of_one() -> None:
    with pytest.raises(ValueError, match="jitter"):
        Backoff(initial_seconds=1.0, jitter=1.0)


def test_rejects_negative_jitter() -> None:
    with pytest.raises(ValueError, match="jitter"):
        Backoff(initial_seconds=1.0, jitter=-0.1)


def test_rejects_a_single_item_tuple() -> None:
    with pytest.raises(ValueError, match="2 or 3 items"):
        Backoff.parse(cast("SleepSecondsType", (7.0,)))


def test_rejects_an_empty_tuple() -> None:
    with pytest.raises(ValueError, match="2 or 3 items"):
        Backoff.parse(cast("SleepSecondsType", ()))


def test_rejects_a_four_item_tuple() -> None:
    with pytest.raises(ValueError, match="2 or 3 items"):
        Backoff.parse(cast("SleepSecondsType", (1.0, 2.0, 3.0, 4.0)))


def test_rejects_none_as_the_initial_interval() -> None:
    with pytest.raises(ValueError, match="only the maximum interval"):
        Backoff.parse(cast("SleepSecondsType", (None, 30.0)))


def test_rejects_a_list_of_intervals() -> None:
    with pytest.raises(TypeError, match="sleep_seconds"):
        Backoff.parse(cast("SleepSecondsType", [1.0, 60.0]))


def test_rejects_a_string_interval() -> None:
    with pytest.raises(TypeError, match="sleep_seconds"):
        Backoff.parse(cast("SleepSecondsType", "30"))


def test_rejects_a_boolean_interval() -> None:
    with pytest.raises(TypeError, match="sleep_seconds"):
        Backoff.parse(cast("SleepSecondsType", bool(1)))


def test_rejects_a_boolean_initial_interval() -> None:
    with pytest.raises(ValueError, match="initial_seconds"):
        Backoff(initial_seconds=cast("float", bool(1)))


def test_rejects_a_boolean_multiplier() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        Backoff(initial_seconds=1.0, multiplier=cast("float", bool(1)))


def test_unbounded_growth_reports_overflow_instead_of_infinity() -> None:
    strategy = Backoff(initial_seconds=1e308, multiplier=2.0)

    with pytest.raises(OverflowError, match="maximum_seconds"):
        list(islice(strategy.delays(), 2))


def test_bounded_growth_never_overflows() -> None:
    strategy = Backoff(initial_seconds=1e308, maximum_seconds=1e308, multiplier=2.0)

    assert_that(strategy).yields_delays([1e308, 1e308, 1e308])


def test_rejects_a_boolean_maximum_interval() -> None:
    with pytest.raises(ValueError, match="maximum_seconds"):
        Backoff(initial_seconds=1.0, maximum_seconds=cast("float", bool(1)))


def test_rejects_a_boolean_jitter() -> None:
    with pytest.raises(ValueError, match="jitter"):
        Backoff(initial_seconds=1.0, jitter=cast("float", bool(1)))
