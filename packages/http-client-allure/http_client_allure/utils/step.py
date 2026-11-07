import httpx

from http_client_allure.settings import StepSettings

from .body import encode_query_params, sanitize_query_params


def build_step_message(request: httpx.Request, settings: StepSettings) -> str:
    """Собрать заголовок Allure шага для запроса.

    Query параметры маскируются так же, как во вложениях: заголовок шага виден в отчете.
    """
    step_message = f"[{request.method}] "

    if settings.show_host:
        step_message += f"{request.url.scheme}://{request.url.host}"

    step_message += request.url.path

    if settings.show_query_params and request.url.query:
        masked = sanitize_query_params(request, settings.sanitize_keys)
        step_message += f"?{encode_query_params(masked)}"

    return step_message
