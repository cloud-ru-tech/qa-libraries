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
    """Option that wraps all HTTP client requests in Allure steps.

    Usage example:
    >>> client = HttpClient(BASE_URL, wrap_requests_in_steps())
    >>> client.get("/sample")

    The step wraps request sending itself, so the report shows its duration,
    and create a failed step for connection errors or timeouts.

    :param show_host: Show the request host in the step, False by default
    :param show_query_params: Show query parameters in the step, False by default
    :param attach_request: Attach request data to the step, True by default
    :param serialize_request_to_curl: Serialize request data as curl, False by default
    :param sanitize_keys: Keys in glom format for masking secrets, None by default
    :param json_dumps_kwargs: JSON serialization options, None by default
    :param max_attach_length: Maximum attachment length in characters, unlimited if None
    :param use_default_sanitize_keys: Extend sanitize_keys with the secret list from http_client,
                                      True by default
    :return: ClientOption option.
    """
    settings = build_settings(**options)

    return _build_option(settings)


def wrap_requests_and_responses_in_steps(**options: Unpack[ResponseStepOptions]) -> ClientOption:
    """Option that wraps all HTTP client requests and responses in Allure steps.

    Usage example:
    >>> client = HttpClient(BASE_URL, wrap_requests_and_responses_in_steps())
    >>> client.get("/sample")

    Unlike wrap_requests_in_steps, also attach response data to the step.
    Attach a placeholder instead of reading a streaming response body.

    Attach response headers and body separately so headers remain visible
    for both empty responses and unread streams. Show the response status in the header
    attachment name.

    :param show_host: Show the request host in the step, False by default
    :param show_query_params: Show query parameters in the step, False by default
    :param attach_request: Attach request data to the step, True by default
    :param attach_response: Attach the response body to the step, True by default
    :param attach_response_headers: Attach response headers to the step, True by default
    :param serialize_request_to_curl: Serialize request data as curl, False by default
    :param sanitize_keys: Keys in glom format for masking secrets, None by default
    :param json_dumps_kwargs: JSON serialization options, None by default
    :param max_attach_length: Maximum attachment length in characters, unlimited if None
    :param use_default_sanitize_keys: Extend sanitize_keys with the secret list from http_client,
                                      True by default
    :return: ClientOption option.
    """
    resolved: ResponseStepOptions = {"attach_response": True, "attach_response_headers": True}
    resolved.update(options)
    settings = build_settings(**resolved)

    return _build_option(settings)


def _build_option(settings: StepSettings) -> ClientOption:
    """Build an option for the client type.

    Unlike event hooks, decorators are not automatically wrapped in coroutines,
    so the asynchronous client needs separate implementations.
    """

    def option(client: BaseHttpClient) -> None:
        if isinstance(client, AsyncHttpClient):
            client.add_send_decorator(async_step_send_decorator(settings))
            client.add_stream_decorator(async_step_stream_decorator(settings))
        else:
            client.add_send_decorator(step_send_decorator(settings))
            client.add_stream_decorator(step_stream_decorator(settings))

    return option
