import time

from .types import Clock
from .validators import validate_timeout_seconds


class Deadline:
    """Дедлайн ожидания, отсчитываемый по монотонным часам.

    Монотонные часы, в отличие от ``time.time``, не сдвигаются при синхронизации по NTP
    и ручном переводе системного времени, поэтому длительность ожидания предсказуема.
    """

    def __init__(self, timeout_seconds: float, *, clock: Clock = time.monotonic) -> None:
        """Инициализировать объект.

        :param timeout_seconds: значение настройки ``timeout_seconds``.
        :param clock: значение настройки ``clock``.
        """
        self._timeout_seconds = validate_timeout_seconds(timeout_seconds)
        self._clock = clock
        self._started_at = clock()

    @property
    def timeout_seconds(self) -> float:
        """Получить заданное максимальное время ожидания в секундах."""
        return self._timeout_seconds

    def elapsed_seconds(self) -> float:
        """Получить время, прошедшее с момента создания дедлайна, в секундах."""
        return self._clock() - self._started_at

    def seconds_remaining(self) -> float:
        """Получить время, оставшееся до дедлайна, в секундах (не меньше нуля)."""
        return max(0.0, self._timeout_seconds - self.elapsed_seconds())
