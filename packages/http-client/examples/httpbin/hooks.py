"""Хуки запросов и ответов плюс собственная опция клиента.

Хуки здесь синхронные и используются обоими клиентами: AsyncHttpClient
оборачивает синхронные хуки в корутины сам, в своём __init__.
"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from logging import Logger

    import httpx
    from http_client import ClientOption
    from http_client.client import BaseHttpClient
    from http_client.types import ResponseHook

API_KEY_HEADER = "X-Api-Key"
STARTED_AT_EXTENSION = "demo_started_at"


def stamp_started_at(request: httpx.Request) -> None:
    """Запомнить момент отправки в extensions запроса.

    extensions — единственное место, которое доживёт до хука ответа:
    оттуда его читает log_elapsed через response.request.
    """
    cast("dict[str, object]", request.extensions)[STARTED_AT_EXTENSION] = perf_counter()


def log_elapsed(logger: Logger) -> ResponseHook:
    """Собрать хук ответа, который пишет длительность запроса.

    :param logger: логгер для записи длительности
    :returns: хук ответа, работающий в паре с stamp_started_at
    """

    def log_elapsed_hook(response: httpx.Response) -> None:
        started_at = cast("dict[str, object]", response.request.extensions).get(STARTED_AT_EXTENSION)
        if not isinstance(started_at, float):
            return

        elapsed_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "Длительность: %s %s -> %s за %.1f мс",
            response.request.method,
            response.request.url.path,
            response.status_code,
            elapsed_ms,
        )

    return log_elapsed_hook


def warn_on_server_error(logger: Logger) -> ResponseHook:
    """Собрать хук ответа, который помечает 5xx предупреждением.

    Тело ответа хук не читает: у потокового ответа оно ещё не загружено,
    а чтение в хуке сломало бы стриминг.

    :param logger: логгер для предупреждений
    :returns: хук ответа
    """

    def warn_on_server_error_hook(response: httpx.Response) -> None:
        if response.is_server_error:
            logger.warning(
                "Сервер вернул %s на %s %s",
                response.status_code,
                response.request.method,
                response.request.url.path,
            )

    return warn_on_server_error_hook


def with_api_key(api_key: str) -> ClientOption:
    """Собрать опцию, добавляющую заголовок X-Api-Key в каждый запрос.

    Хук встаёт в начало списка, поэтому заголовок попадёт в лог независимо от того,
    в каком порядке опцию передали конструктору: with_logger добавляет свой хук в конец.
    Опция, которой не нужна позиция в списке, должна собираться из with_request_hook.

    :param api_key: значение заголовка
    :returns: опция клиента
    """

    def add_api_key(request: httpx.Request) -> None:
        request.headers[API_KEY_HEADER] = api_key

    def option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_api_key, prepend=True)

    return option
