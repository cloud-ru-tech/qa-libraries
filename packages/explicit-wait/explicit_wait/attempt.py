from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attempt:
    """Результат одной попытки ожидания, передаваемый в хуки.

    Ровно одно из полей ``result`` и ``exception`` осмысленно: если предикат завершился
    исключением из ``expected_exceptions``, то ``exception`` заполнен, а ``result`` равен None.
    """

    number: int
    elapsed_seconds: float
    result: object = None
    exception: Exception | None = None
    next_sleep_seconds: float | None = None

    @property
    def has_no_planned_sleep(self) -> bool:
        """Проверить, что на момент решения следующая пауза не запланирована.

        Это снимок плана, а не гарантия финальности: попытка может оказаться последней и при
        запланированной паузе, если ожидание отменят извне, пробуждение случится позже
        заказанного или время израсходует сам хук.
        """
        return self.next_sleep_seconds is None
