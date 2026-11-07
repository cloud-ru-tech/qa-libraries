from typing import cast

from http_client import AsyncHttpClient, BaseHttpClient, ClientOption
from http_client import options as http_options

from .config import NO_OVERRIDES, RetryOverrides
from .decorators import async_stream_decorator, send_decorator, stream_decorator
from .policy import ResponseCondition, RetryPolicy

# Политика хранится на самом клиенте: обе опции наполняют один экземпляр, чтобы запрос
# обслуживал единый цикл повторов с общим бюджетом попыток.
_POLICY_ATTR = "_http_client_retries_policy"


def with_retries_failed_requests(
    *,
    overrides: RetryOverrides = NO_OVERRIDES,
) -> ClientOption:
    """Опция для повторных попыток запросов при ошибках соединения с сервером.

    Применяется и к обычным, и к потоковым запросам.

    Поля ``overrides``, оставленные по умолчанию, берутся из глобальной конфигурации в момент запроса,
    поэтому поздний вызов `configure()` всё ещё действует. Переданные значения перекрывают её
    только для этого клиента; ``RetryOverrides(before_sleep_hook=None)`` отключает глобальный хук.

    :param overrides: переопределения глобальной политики для этого клиента.
    :return: опция настройки клиента.
    """

    def option(client: BaseHttpClient) -> None:
        policy = _policy_of(client)
        policy.retry_on_network_errors = True
        policy.overrides = policy.overrides.merge(overrides)

    return option


def with_retries_if(
    retry_condition: ResponseCondition,
    *,
    overrides: RetryOverrides = NO_OVERRIDES,
) -> ClientOption:
    """Опция для повторных попыток запросов при выполнении условия retry_condition.

    Применяется и к обычным, и к потоковым запросам. Для потока условие проверяется
    сразу после открытия потока, пока тело ответа ещё не прочитано.

    Правила переопределения политики те же, что у :func:`with_retries_failed_requests`.
    Если опция используется вместе с другими опциями повторов, все условия работают
    в одном цикле с общим бюджетом попыток.

    :param retry_condition: условие, при котором ответ требует повтора.
    :param overrides: переопределения глобальной политики для этого клиента.
    :return: опция настройки клиента.
    """

    def option(client: BaseHttpClient) -> None:
        policy = _policy_of(client)
        policy.conditions.append(retry_condition)
        policy.overrides = policy.overrides.merge(overrides)

    return option


def _policy_of(client: BaseHttpClient) -> RetryPolicy:
    """Вернуть политику клиента, создав её и подключив декораторы при первом обращении."""
    policy = cast("RetryPolicy | None", getattr(client, _POLICY_ATTR, None))
    if policy is not None:
        return policy

    policy = RetryPolicy()
    setattr(client, _POLICY_ATTR, policy)

    # Декораторы регистрируются один раз и читают политику в момент запроса,
    # поэтому условия, добавленные следующими опциями, тоже учитываются.
    http_options.with_send_decorator(send_decorator(policy))(client)

    build_stream_decorator = async_stream_decorator if isinstance(client, AsyncHttpClient) else stream_decorator
    http_options.with_stream_decorator(build_stream_decorator(policy))(client)

    return policy
