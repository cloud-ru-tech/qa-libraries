from typing import Unpack

from http_client import AsyncHttpClient, BaseHttpClient, ClientOption

from .decorators import (
    async_step_send_decorator,
    async_step_stream_decorator,
    step_send_decorator,
    step_stream_decorator,
)
from .settings import RequestStepOptions, ResponseStepOptions, StepSettings, build_settings


def wrap_requests_in_steps(**options: Unpack[RequestStepOptions]) -> ClientOption:
    """Опция для обертки всех запросов HTTP-клиента в шаги Allure.

    Пример использования:
    >>> client = HttpClient(BASE_URL, wrap_requests_in_steps())
    >>> client.get("/sample")

    Шаг оборачивает саму отправку запроса, поэтому в отчете видна ее длительность,
    а при ошибке соединения или таймауте шаг создается и помечается упавшим.

    :param show_host: отображать хост запроса в шаге, по умолчанию False
    :param show_query_params: отображать параметры запроса в шаге, по умолчанию False
    :param attach_request: прикреплять данные запроса к шагу, по умолчанию True
    :param serialize_request_to_curl: сериализовать данные запроса в curl, по умолчанию False
    :param sanitize_keys: ключи в формате glom для скрытия секретных данных, по умолчанию None
    :param json_dumps_kwargs: параметры сериализации JSON, по умолчанию None
    :param max_attach_length: максимальная длина вложения в символах, если None - без ограничений
    :param use_default_sanitize_keys: дополнять sanitize_keys списком секретов из http_client,
                                      по умолчанию True
    :return: опция ClientOption.
    """
    settings = build_settings(**options)

    return _build_option(settings)


def wrap_requests_and_responses_in_steps(**options: Unpack[ResponseStepOptions]) -> ClientOption:
    """Опция для обертки всех запросов и ответов HTTP-клиента в шаги Allure.

    Пример использования:
    >>> client = HttpClient(BASE_URL, wrap_requests_and_responses_in_steps())
    >>> client.get("/sample")

    Отличается от wrap_requests_in_steps тем, что к шагу прикрепляются еще и данные ответа.
    Тело потокового ответа не читается, вместо него прикрепляется заглушка.

    Заголовки и тело ответа прикрепляются отдельными вложениями, поэтому заголовки видны
    и у ответа без тела, и у непрочитанного потока. Статус ответа отображается в имени
    вложения с заголовками.

    :param show_host: отображать хост запроса в шаге, по умолчанию False
    :param show_query_params: отображать параметры запроса в шаге, по умолчанию False
    :param attach_request: прикреплять данные запроса к шагу, по умолчанию True
    :param attach_response: прикреплять тело ответа к шагу, по умолчанию True
    :param attach_response_headers: прикреплять заголовки ответа к шагу, по умолчанию True
    :param serialize_request_to_curl: сериализовать данные запроса в curl, по умолчанию False
    :param sanitize_keys: ключи в формате glom для скрытия секретных данных, по умолчанию None
    :param json_dumps_kwargs: параметры сериализации JSON, по умолчанию None
    :param max_attach_length: максимальная длина вложения в символах, если None - без ограничений
    :param use_default_sanitize_keys: дополнять sanitize_keys списком секретов из http_client,
                                      по умолчанию True
    :return: опция ClientOption.
    """
    resolved: ResponseStepOptions = {"attach_response": True, "attach_response_headers": True}
    resolved.update(options)
    settings = build_settings(**resolved)

    return _build_option(settings)


def _build_option(settings: StepSettings) -> ClientOption:
    """Собрать опцию под тип клиента.

    Декораторы, в отличие от event hooks, не оборачиваются в корутины автоматически,
    поэтому для асинхронного клиента нужны свои реализации.
    """

    def option(client: BaseHttpClient) -> None:
        if isinstance(client, AsyncHttpClient):
            client.add_send_decorator(async_step_send_decorator(settings))
            client.add_stream_decorator(async_step_stream_decorator(settings))
        else:
            client.add_send_decorator(step_send_decorator(settings))
            client.add_stream_decorator(step_stream_decorator(settings))

    return option
