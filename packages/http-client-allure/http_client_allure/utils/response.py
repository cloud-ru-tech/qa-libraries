import json
from typing import cast

import allure
import httpx
from http_client.utils import sanitizer

from http_client_allure.settings import StepSettings

from .attachment import Attachment
from .body import JSON_CONTENT_TYPE, STREAMED_CONTENT, UNPARSED, decode, parse_json_body


def parse_response_headers_for_attach(response: httpx.Response, settings: StepSettings) -> Attachment:
    """Build an attachment with response headers.

    httpx joins repeated headers with commas, matching the request attachment.

    :param response: HTTP response
    :param settings: Step settings
    :return: Attachment for the step
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
    """Build an attachment with the response body.

    :param response: HTTP response
    :param body: Response body; None indicates an unread stream
    :param settings: Step settings
    :return: Attachment, or None if the response body is empty
    """
    name = "Response content"

    if body is None:
        return Attachment(name=name, content=STREAMED_CONTENT, type=allure.attachment_type.TEXT)

    if not body:
        return None

    text = decode(body)

    if cast("str", response.headers.get("content-type", "")).startswith(JSON_CONTENT_TYPE):
        # Track parsing separately from the value type: valid JSON can also be a string
        parsed = parse_json_body(text, settings.sanitize_keys)
        if parsed is not UNPARSED:
            return Attachment(
                name=name,
                content=json.dumps(parsed, **settings.json_dumps_kwargs),
                type=allure.attachment_type.JSON,
            )

    return Attachment(name=name, content=text, type=allure.attachment_type.TEXT)
