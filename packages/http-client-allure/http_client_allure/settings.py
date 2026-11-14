from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypedDict, Unpack

from http_client.event_hooks import DEFAULT_SANITIZE_KEYS
from httpx_curlify.curlify import JsonDumpsOptions

DEFAULT_JSON_DUMPS_KWARGS: JsonDumpsOptions = {"ensure_ascii": False}


class RequestStepOptions(TypedDict, total=False):
    """Step and request attachment settings."""

    show_host: bool
    show_query_params: bool
    attach_request: bool
    serialize_request_to_curl: bool
    sanitize_keys: Sequence[str] | None
    json_dumps_kwargs: JsonDumpsOptions | None
    max_attach_length: int | None
    use_default_sanitize_keys: bool


class ResponseStepOptions(RequestStepOptions, total=False):
    """Step settings with request and response attachments."""

    attach_response: bool
    attach_response_headers: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class StepSettings:
    """Allure step formatting options for one HTTP request."""

    show_host: bool = False
    show_query_params: bool = False
    attach_request: bool = True
    attach_response: bool = False
    attach_response_headers: bool = False
    serialize_request_to_curl: bool = False
    sanitize_keys: tuple[str, ...] = DEFAULT_SANITIZE_KEYS
    json_dumps_kwargs: JsonDumpsOptions = field(default_factory=DEFAULT_JSON_DUMPS_KWARGS.copy)
    max_attach_length: int | None = None


def build_settings(**options: Unpack[ResponseStepOptions]) -> StepSettings:
    """Build step settings with the resolved names of fields to mask.

    :param options: Step and attachment settings.
    :return: Immutable step settings.
    """
    default_keys = DEFAULT_SANITIZE_KEYS if options.get("use_default_sanitize_keys", True) else ()
    resolved_keys: list[str] = []
    for key in (*default_keys, *(options.get("sanitize_keys") or ())):
        if key not in resolved_keys:
            resolved_keys.append(key)
    return StepSettings(
        show_host=options.get("show_host", False),
        show_query_params=options.get("show_query_params", False),
        attach_request=options.get("attach_request", True),
        attach_response=options.get("attach_response", False),
        attach_response_headers=options.get("attach_response_headers", False),
        serialize_request_to_curl=options.get("serialize_request_to_curl", False),
        sanitize_keys=tuple(resolved_keys),
        json_dumps_kwargs=options.get("json_dumps_kwargs") or DEFAULT_JSON_DUMPS_KWARGS.copy(),
        max_attach_length=options.get("max_attach_length"),
    )
