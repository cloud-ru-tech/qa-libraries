import httpx

from http_client_allure.settings import StepSettings

from .body import encode_query_params, sanitize_query_params


def build_step_message(request: httpx.Request, settings: StepSettings) -> str:
    """Build an Allure step title for the request.

    Mask query parameters as in attachments: the step title is visible in the report.
    """
    step_message = f"[{request.method}] "

    if settings.show_host:
        step_message += f"{request.url.scheme}://{request.url.host}"

    step_message += request.url.path

    if settings.show_query_params and request.url.query:
        masked = sanitize_query_params(request, settings.sanitize_keys)
        step_message += f"?{encode_query_params(masked)}"

    return step_message
