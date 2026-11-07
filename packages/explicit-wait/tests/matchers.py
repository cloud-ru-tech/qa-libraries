from __future__ import annotations

from itertools import islice
from typing import TYPE_CHECKING, Self, cast

from assertpy.assertpy import AssertionBuilder

DELAY_TOLERANCE = 1e-9


if TYPE_CHECKING:
    from collections.abc import Sequence

    from explicit_wait import Backoff
    from explicit_wait.backoff import RandomSource

    _Assertions = AssertionBuilder[object]
else:
    _Assertions = AssertionBuilder


class WaitAssertions(_Assertions):
    """Проверки, специфичные для библиотеки ожиданий."""

    def yields_delays(self, expected: Sequence[float], *, rng: RandomSource | None = None) -> Self:
        """Проверить, что стратегия выдаёт ожидаемую последовательность пауз.

        :param expected: ожидаемые паузы в секундах.
        :param rng: источник случайности для jitter.
        :return: тот же объект проверок.
        """
        actual = self._take_delays(len(expected), rng)
        mismatched = [
            (index, actual_delay, expected_delay)
            for index, (actual_delay, expected_delay) in enumerate(zip(actual, expected, strict=True))
            if abs(actual_delay - expected_delay) > DELAY_TOLERANCE
        ]
        if mismatched:
            self.error(f"Expected delays <{list(expected)}>, but was <{actual}>, mismatch at {mismatched}")
        return self

    def yields_delays_between(self, lower: float, upper: float, *, count: int) -> Self:
        """Проверить, что все паузы попадают в заданный диапазон.

        :param lower: нижняя граница включительно.
        :param upper: верхняя граница включительно.
        :param count: сколько пауз проверять.
        :return: тот же объект проверок.
        """
        actual = self._take_delays(count, None)
        outliers = [delay for delay in actual if not lower <= delay <= upper]
        if outliers:
            self.error(f"Expected every delay within <[{lower}, {upper}]>, but <{outliers}> fell outside")
        return self

    def _take_delays(self, count: int, rng: RandomSource | None) -> list[float]:
        return list(islice(cast("Backoff", self.val).delays(rng), count))


def assert_that(actual: object) -> WaitAssertions:
    """Начать проверку значения.

    :param actual: проверяемое значение.
    :return: объект проверок.
    """
    return WaitAssertions(actual)
