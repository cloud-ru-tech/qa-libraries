import math
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

TUPLE_MULTIPLIER = 2.0
SHORT_TUPLE_LENGTH = 2
FULL_TUPLE_LENGTH = 3

SleepSecondsType = float | tuple[float, float | None] | tuple[float, float | None, float]

# SystemRandom вместо RandomSource: jitter не связан с безопасностью, но так не нужно
# подавлять предупреждение линтера о небезопасном генераторе.
_shared_rng = secrets.SystemRandom()


class RandomSource(Protocol):
    """Источник случайной доли для jitter."""

    def random(self) -> float:
        """Получить число в интервале от нуля включительно до единицы.

        :return: случайная доля.
        """
        ...


@dataclass(frozen=True, slots=True)
class Backoff:
    """Стратегия роста паузы между попытками ожидания.

    Пауза начинается с ``initial_seconds`` и умножается на ``multiplier`` после каждой
    попытки, не превышая ``maximum_seconds``. При ``jitter`` больше нуля из каждой паузы
    случайно вычитается до ``jitter``-й доли, чтобы параллельные тесты не били
    в один и тот же сервис синхронными волнами запросов.
    """

    initial_seconds: float
    maximum_seconds: float | None = None
    multiplier: float = 1.0
    jitter: float = 0.0

    def __post_init__(self) -> None:
        """Проверить корректность параметров стратегии.

        :raises ValueError: если значения выходят за допустимые границы.
        """
        self._validate_initial_seconds()
        self._validate_maximum_seconds()
        self._validate_multiplier()
        self._validate_jitter()

    @classmethod
    def parse(cls, sleep_seconds: "SleepSecondsType | Backoff") -> "Backoff":
        """Привести значение параметра ``sleep_seconds`` к стратегии роста паузы.

        :param sleep_seconds: число (постоянная пауза), кортеж
            ``(начальная, максимальная[, множитель])`` или готовый ``Backoff``.
        :return: стратегия роста паузы.
        :raises TypeError: если передан неподдерживаемый тип.
        :raises ValueError: если кортеж имеет неверную длину или значения некорректны.
        """
        if isinstance(sleep_seconds, Backoff):
            return sleep_seconds
        if isinstance(sleep_seconds, tuple):
            return cls._parse_tuple(sleep_seconds)
        if isinstance(sleep_seconds, int | float) and not isinstance(sleep_seconds, bool):
            return cls(initial_seconds=float(sleep_seconds))
        message = (
            f"sleep_seconds must be a number, a tuple of 2-3 numbers or a Backoff, got {type(sleep_seconds).__name__}"
        )
        raise TypeError(
            message,
        )

    def delays(self, rng: RandomSource | None = None) -> Iterator[float]:
        """Получить бесконечную последовательность пауз между попытками.

        :param rng: источник случайности для ``jitter``; по умолчанию общий на процесс.
        :return: итератор пауз в секундах.
        """
        source = _shared_rng if rng is None else rng
        delay = self.initial_seconds
        while True:
            yield self._apply_jitter(delay, source)
            delay = self._grow(delay)

    @classmethod
    def _parse_tuple(cls, sleep_seconds: tuple[float | None, ...]) -> "Backoff":
        if len(sleep_seconds) not in (SHORT_TUPLE_LENGTH, FULL_TUPLE_LENGTH):
            message = f"sleep_seconds tuple must contain 2 or 3 items, got {len(sleep_seconds)}"
            raise ValueError(
                message,
            )
        initial = sleep_seconds[0]
        multiplier = TUPLE_MULTIPLIER if len(sleep_seconds) == SHORT_TUPLE_LENGTH else sleep_seconds[2]
        if initial is None or multiplier is None:
            message = f"only the maximum interval of a sleep_seconds tuple may be None, got {sleep_seconds!r}"
            raise ValueError(
                message,
            )
        return cls(
            initial_seconds=initial,
            maximum_seconds=sleep_seconds[1],
            multiplier=multiplier,
        )

    def _grow(self, delay: float) -> float:
        grown = delay * self.multiplier
        if self.maximum_seconds is not None:
            return min(grown, self.maximum_seconds)
        if not math.isfinite(grown):
            message = "backoff delay overflowed to infinity; set maximum_seconds to bound the growth"
            raise OverflowError(
                message,
            )
        return grown

    def _apply_jitter(self, delay: float, rng: RandomSource) -> float:
        if self.jitter == 0:
            return delay
        return delay * (1.0 - self.jitter * rng.random())

    def _validate_initial_seconds(self) -> None:
        if not _is_number(self.initial_seconds):
            message = f"initial_seconds must be a number, got {type(self.initial_seconds).__name__}"
            raise ValueError(
                message,
            )
        if not math.isfinite(self.initial_seconds) or self.initial_seconds <= 0:
            message = f"initial_seconds must be a finite positive number, got {self.initial_seconds!r}"
            raise ValueError(
                message,
            )

    def _validate_maximum_seconds(self) -> None:
        if self.maximum_seconds is None:
            return
        if not _is_number(self.maximum_seconds):
            message = f"maximum_seconds must be a number or None, got {type(self.maximum_seconds).__name__}"
            raise ValueError(
                message,
            )
        if not math.isfinite(self.maximum_seconds):
            message = f"maximum_seconds must be a finite number or None, got {self.maximum_seconds!r}"
            raise ValueError(
                message,
            )
        if self.maximum_seconds < self.initial_seconds:
            message = (
                f"maximum_seconds {self.maximum_seconds!r} must not be less than "
                f"initial_seconds {self.initial_seconds!r}"
            )
            raise ValueError(
                message,
            )

    def _validate_multiplier(self) -> None:
        if not _is_number(self.multiplier):
            message = f"multiplier must be a number, got {type(self.multiplier).__name__}"
            raise ValueError(
                message,
            )
        if not math.isfinite(self.multiplier) or self.multiplier < 1:
            message = f"multiplier must be a finite number not less than 1, got {self.multiplier!r}"
            raise ValueError(
                message,
            )

    def _validate_jitter(self) -> None:
        if not _is_number(self.jitter):
            message = f"jitter must be a number, got {type(self.jitter).__name__}"
            raise ValueError(message)
        if not math.isfinite(self.jitter) or not 0 <= self.jitter < 1:
            message = f"jitter must be a number in range [0, 1), got {self.jitter!r}"
            raise ValueError(message)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
