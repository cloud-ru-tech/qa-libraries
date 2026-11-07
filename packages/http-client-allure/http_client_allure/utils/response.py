import json
from typing import cast

import allure
import httpx
from http_client.utils import sanitizer

from http_client_allure.settings import StepSettings

from .attachment import Attachment
from .body import JSON_CONTENT_TYPE, STREAMED_CONTENT, UNPARSED, decode, parse_json_body


def parse_response_headers_for_attach(response: httpx.Response, settings: StepSettings) -> Attachment:
    """Собрать вложение с заголовками ответа.

    Повторяющиеся заголовки httpx склеивает через запятую - так же, как во вложении запроса.

    :param response: HTTP-ответ
    :param settings: настройки шага
    :return: вложение для прикрепления к шагу
    """
    return Attachment(
        name=f"Response headers: status = {response.status_code} [{response.reason_phrase}]",
        content=json.dumps(
            sanitizer.sanitize(dict(response.headers), settings.sanitize_keys),
            **settings.json_dumps_kwargs,
        ),
        type=allure.attachment_type.JSON,
    )


def parse_response_for_attach(
    response: httpx.Response,
    body: bytes | None,
    settings: StepSettings,
) -> Attachment | None:
    """Собрать вложение с телом ответа.

    :param response: HTTP-ответ
    :param body: тело ответа, None означает непрочитанный поток
    :param settings: настройки шага
    :return: вложение либо None, если тело ответа пустое
    """
    name = "Response content"

    if body is None:
        return Attachment(name=name, content=STREAMED_CONTENT, type=allure.attachment_type.TEXT)

    if not body:
        return None

    text = decode(body)

    if cast("str", response.headers.get("content-type", "")).startswith(JSON_CONTENT_TYPE):
        # Признак разбора нужен отдельно от типа значения: валидный JSON тоже бывает строкой
        parsed = parse_json_body(text, settings.sanitize_keys)
        if parsed is not UNPARSED:
            return Attachment(
                name=name,
                content=json.dumps(parsed, **settings.json_dumps_kwargs),
                type=allure.attachment_type.JSON,
            )

    return Attachment(name=name, content=text, type=allure.attachment_type.TEXT)
