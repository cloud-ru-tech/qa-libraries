"""Политика повторов: что повторять и с какими параметрами."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import httpcore
import httpx
from httpx import Response
from tenacity import RetryCallState, retry_if_result, retry_never
from tenacity.retry import retry_base

from ._types import is_http_response
from .config import NO_OVERRIDES, Config, RetryOverrides, get_config

#: Сетевые ошибки, при которых запрос имеет смысл повторить.
RETRYABLE_EXCEPTIONS = (httpx.RequestError, httpcore.NetworkError, httpcore.PoolTimeout)

#: Исключения из :data:`RETRYABLE_EXCEPTIONS`: формально это `RequestError`, но повтор того же
#: запроса даст ровно тот же результат, только потратив весь бюджет попыток и все паузы.
NON_RETRYABLE_EXCEPTIONS = (
    httpx.TooManyRedirects,
    httpx.UnsupportedProtocol,
    httpx.DecodingError,
    httpx.LocalProtocolError,
)


class retry_transient_errors(retry_base):  # noqa: N801 - соглашение об именовании стратегий tenacity
    """Повторять сетевые ошибки, кроме заведомо детерминированных."""

    def __call__(self, retry_state: RetryCallState) -> bool:
        """Определить, нужно ли повторить неудачную попытку.

        :param retry_state: состояние последней попытки.
        :return: требуется ли повтор.
        """
        outcome = retry_state.outcome
        if outcome is None or not outcome.failed:
            return False

        error = outcome.exception()

        return isinstance(error, RETRYABLE_EXCEPTIONS) and not isinstance(error, NON_RETRYABLE_EXCEPTIONS)


# Пометка на ответе, не прошедшем условие повтора. Живёт в extensions, чтобы наружу
# (в том числе в RetryError.last_attempt.result()) уходил обычный Response.
REJECTED_EXTENSION = "http_client_retries.rejected"

ResponseCondition = Callable[[Response], bool]


@dataclass
class RetryPolicy:
    """Единая политика повторов одного клиента.

    Обе опции наполняют один экземпляр, поэтому запрос обслуживает один цикл tenacity
    с общим бюджетом попыток. Раньше каждая опция заводила собственный цикл, и лимиты
    перемножались: при `stop_after_attempt(5)` в транспорт могло уйти до 25 запросов.
    """

    retry_on_network_errors: bool = False
    conditions: list[ResponseCondition] = field(default_factory=list)
    overrides: RetryOverrides = NO_OVERRIDES

    def rejects(self, response: Response) -> bool:
        """Просит ли хотя бы одно условие повторить этот ответ."""
        return any(condition(response) for condition in self.conditions)

    def resolve_config(self) -> Config:
        """Текущая конфигурация с учётом переопределений клиента.

        Читается на каждый запрос: `configure()` может поменять политику уже после
        того, как клиент создан.
        """
        return self.overrides.apply_to(get_config())

    def build_strategy(self) -> retry_base:
        """Собрать условие повтора для tenacity."""
        by_error = retry_transient_errors() if self.retry_on_network_errors else None
        by_result = retry_if_result(self._is_rejected) if self.conditions else None

        if by_error is not None and by_result is not None:
            return by_error | by_result

        return by_error or by_result or retry_never

    def _is_rejected(self, result: object) -> bool:
        # Для ответа условие уже проверено при попытке — здесь только читаем пометку,
        # чтобы пользовательский предикат не вызывался дважды.
        if is_http_response(result):
            return bool(cast("dict[str, object]", result.extensions).get(REJECTED_EXTENSION, False))

        return self.rejects(cast("Response", result))


def set_rejected(response: Response, *, rejected: bool) -> None:
    """Проставить или снять пометку об отклонении.

    Снимать обязательно: объект ответа может переиспользоваться между попытками,
    и залипшая пометка заставила бы повторять уже принятый ответ.
    """
    if rejected:
        cast("dict[str, object]", response.extensions)[REJECTED_EXTENSION] = True
    else:
        cast("dict[str, object]", response.extensions).pop(REJECTED_EXTENSION, None)
