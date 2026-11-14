import json
from typing import cast

import allure
import httpx
from http_client.utils import sanitizer
from httpx_curlify import to_curl

from http_client_allure.settings import StepSettings

from .attachment import Attachment
from .body import JSON_CONTENT_TYPE, STREAMED_CONTENT, encode_query_params, render_body, sanitize_query_params


def parse_request_for_attach(
    request: httpx.Request,
    body: bytes | None,
    settings: StepSettings,
) -> Attachment:
    """Build an attachment with request data.

    :param request: HTTP request
    :param body: Request body; None indicates an unread upload stream
    :param settings: Step settings
    :return: Attachment for the step
    """
    if settings.serialize_request_to_curl:
        return _build_curl_attachment(request, body, settings)

    return _build_json_attachment(request, body, settings)


def _build_curl_attachment(
    request: httpx.Request,
    body: bytes | None,
    settings: StepSettings,
) -> Attachment:
    return Attachment(
        name="Request curl",
        content=to_curl(
            _build_curl_request(request, body, settings),
            settings.sanitize_keys,
            settings.json_dumps_kwargs,
        ),
        type=allure.attachment_type.TEXT,
    )


def _build_curl_request(
    request: httpx.Request,
    body: bytes | None,
    settings: StepSettings,
) -> httpx.Request:
    """Rebuild a request for to_curl with a masked URL and a prepared body.

    Do not pass the original request: to_curl prints the URL unchanged, exposing query
    secrets in the report, and reads the body itself, consuming an unread upload stream
    before sending and causing the request to fail with StreamClosed.
    """
    return httpx.Request(
        request.method,
        _sanitized_url(request, settings),
        headers=request.headers,
        content=body if body is not None else _streamed_placeholder(request),
    )


def _streamed_placeholder(request: httpx.Request) -> bytes:
    """Create a placeholder for an unread streaming upload body.

    For a JSON request, the placeholder must be valid JSON: to_curl parses
    the body with json.loads and would fail on a plain string after sending.
    """
    if cast("str", request.headers.get("content-type", "")).startswith(JSON_CONTENT_TYPE):
        return json.dumps(STREAMED_CONTENT).encode()

    return STREAMED_CONTENT.encode()


def _build_json_attachment(
    request: httpx.Request,
    body: bytes | None,
    settings: StepSettings,
) -> Attachment:
    content: dict[str, object] = {
        "method": request.method,
        "url": str(request.url.copy_with(query=None)),
    }

    if request.url.query:
        content["query_params"] = sanitize_query_params(request, settings.sanitize_keys)

    content["headers"] = sanitizer.sanitize(dict(request.headers), settings.sanitize_keys)
    content["body"] = render_body(
        body,
        cast("str", request.headers.get("content-type", "")),
        settings.sanitize_keys,
    )

    return Attachment(
        name="Request details",
        content=json.dumps(content, **settings.json_dumps_kwargs),
        type=allure.attachment_type.JSON,
    )


def _sanitized_url(request: httpx.Request, settings: StepSettings) -> httpx.URL:
    if not request.url.query:
        return request.url

    masked = sanitize_query_params(request, settings.sanitize_keys)

    return request.url.copy_with(query=encode_query_params(masked).encode())
