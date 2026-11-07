"""Учёт заголовка ответа `Retry-After` при выборе паузы между попытками."""

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import cast

from tenacity import RetryCallState
from tenacity.wait import WaitBaseT, wait_base

from ._types import is_http_response

RETRY_AFTER_HEADER = "Retry-After"


def parse_retry_after(value: str, now: datetime | None = None) -> float | None:
    """Разобрать значение `Retry-After`: либо секунды, либо HTTP-дата.

    Возвращает паузу в секундах или `None`, если значение нечитаемо. Отрицательное число
    секунд считается нечитаемым: по спецификации задержка неотрицательна, и подставлять
    вместо неё немедленный повтор было бы самодеятельностью.

    :param now: точка отсчёта для HTTP-даты. Дата без часового пояса трактуется как UTC.
    """
    raw = value.strip()
    if not raw:
        return None

    seconds = _parse_seconds(raw)
    if seconds is not None:
        return seconds

    return _parse_http_date(raw, _as_aware(now) if now is not None else datetime.now(UTC))


def _as_aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _parse_seconds(raw: str) -> float | None:
    try:
        seconds = float(raw)
    except ValueError:
        return None

    if not math.isfinite(seconds) or seconds < 0:
        return None

    return seconds


def _parse_http_date(raw: str, now: datetime) -> float | None:
    try:
        deadline = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None

    # Дата в прошлом — валидное «можно повторять прямо сейчас», в отличие от отрицательных секунд.
    return max(0.0, (_as_aware(deadline) - now).total_seconds())


class wait_retry_after(wait_base):  # noqa: N801 - соглашение об именовании стратегий tenacity
    """Ждать столько, сколько просит сервер, иначе — по запасной стратегии.

    Пауза из `Retry-After` ограничена сверху: сервер может попросить и час,
    а держать вызывающий код заблокированным всё это время нельзя.
    """

    def __init__(self, fallback: WaitBaseT, maximum: float) -> None:
        """Инициализировать объект.

        :param fallback: значение настройки ``fallback``.
        :param maximum: значение настройки ``maximum``.
        """
        if not math.isfinite(maximum) or maximum < 0:
            message = f"Верхняя граница паузы должна быть конечным неотрицательным числом, получено {maximum!r}"
            raise ValueError(message)

        self._fallback = fallback
        self._maximum = maximum

    def __call__(self, retry_state: RetryCallState) -> float:
        """Определить паузу перед следующей попыткой.

        :param retry_state: состояние последней попытки.
        :return: пауза в секундах.
        """
        requested = self._requested_delay(retry_state)
        if requested is None:
            return self._fallback(retry_state)

        return min(requested, self._maximum)

    def _requested_delay(self, retry_state: RetryCallState) -> float | None:
        outcome = retry_state.outcome
        if outcome is None or outcome.failed:
            return None

        response = cast("object", outcome.result())
        if not is_http_response(response):
            return None

        header = cast("str | None", response.headers.get(RETRY_AFTER_HEADER))

        return parse_retry_after(header) if header else None
