import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from http_client import HttpClient, options
from http_client_allure.options import wrap_requests_in_steps

from .config import BASE_URL, SRC_ROOT

if TYPE_CHECKING:
    from .json_types import JsonValue


@dataclass(slots=True)
class Scenario:
    """Client, request and expected step title for one case."""

    client: HttpClient
    request: httpx.Request
    step_message: str
    prepare_snapshot: Callable[[str], str] = lambda x: x


def case_simple_get_request() -> Scenario:
    client = HttpClient("https://example.com", wrap_requests_in_steps())
    return _create_simple_get_request_case(client)


def case_simple_get_curl_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps(serialize_request_to_curl=True))
    return _create_simple_get_request_case(client)


def case_get_request_with_params_in_step_message() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps(show_host=True, show_query_params=True))
    return Scenario(
        client=client,
        step_message=f"[GET] {BASE_URL}/api/v2/get?name=Alexandr&is_active=true&age=30",
        request=client.client.build_request(
            method="GET",
            url="/api/v2/get",
            params={"name": "Alexandr", "is_active": True, "age": 30},
        ),
    )


def case_json_request_without_json_dumps_kwargs() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps())
    return _create_json_request_case(client)


def case_json_curl_request_without_json_dumps_kwargs() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps(serialize_request_to_curl=True))
    return _create_json_request_case(client)


def case_json_request_with_json_dumps_kwargs() -> Scenario:
    client = HttpClient(
        BASE_URL,
        wrap_requests_in_steps(
            json_dumps_kwargs={
                "indent": 2,
                "ensure_ascii": False,
                "sort_keys": True,
            },
        ),
    )
    return _create_json_request_case(client)


def case_json_curl_request_with_json_dumps_kwargs() -> Scenario:
    client = HttpClient(
        BASE_URL,
        wrap_requests_in_steps(
            serialize_request_to_curl=True,
            json_dumps_kwargs={
                "indent": 2,
                "ensure_ascii": False,
                "sort_keys": True,
            },
        ),
    )
    return _create_json_request_case(client)


def case_multipart_text_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps())
    return _create_multipart_text_request_case(client)


def case_multipart_text_curl_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps(serialize_request_to_curl=True))
    return _create_multipart_text_request_case(client)


def case_multipart_binary_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps())
    return _create_multipart_binary_request_case(client)


def case_multipart_binary_curl_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps(serialize_request_to_curl=True))
    return _create_multipart_binary_request_case(client)


def case_urlencoded_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps())
    return _create_urlencoded_request_case(client)


def case_urlencoded_curl_request() -> Scenario:
    client = HttpClient(BASE_URL, wrap_requests_in_steps(serialize_request_to_curl=True))
    return _create_urlencoded_request_case(client)


def case_json_request_with_sanitize_keys() -> Scenario:
    client = HttpClient(
        BASE_URL,
        options.with_auth(httpx.BasicAuth("admin", "123123")),
        wrap_requests_in_steps(
            sanitize_keys=["data.password", "authorization"],
        ),
    )
    return _create_json_request_with_sensitive_data(client)


def case_json_curl_request_with_sanitize_keys() -> Scenario:
    client = HttpClient(
        BASE_URL,
        options.with_auth(httpx.BasicAuth("admin", "123123")),
        wrap_requests_in_steps(
            sanitize_keys=["data.password", "authorization"],
            serialize_request_to_curl=True,
        ),
    )
    return _create_json_request_with_sensitive_data(client)


def _create_simple_get_request_case(client: HttpClient) -> Scenario:
    return Scenario(
        client=client,
        step_message="[GET] /api/v2/get",
        request=client.client.build_request(
            method="GET",
            url="/api/v2/get",
            params={"name": "Alexandr", "is_active": True, "age": 30},
        ),
    )


def _create_json_request_case(client: HttpClient) -> Scenario:
    json_payload_1: dict[str, JsonValue] = {
        "data": [
            {
                "name": "Alexandr",
                "age": 30,
                "address": None,
            },
            {
                "name": "Aleksey",
                "age": 25,
                "address": "Санкт-Петербург",
            },
        ],
    }
    return Scenario(
        client=client,
        step_message="[POST] /api/v2/users",
        request=client.client.build_request(
            method="POST",
            url="/api/v2/users",
            json=json_payload_1,
        ),
    )


def _create_multipart_text_request_case(client: HttpClient) -> Scenario:
    return Scenario(
        client=client,
        step_message="[POST] /api/v1/upload",
        request=client.client.build_request(
            method="POST",
            url="/api/v1/upload",
            files={
                "file": (
                    "poem.txt",
                    (SRC_ROOT / "data" / "file.txt").read_bytes(),
                )
            },
        ),
        prepare_snapshot=_prepare_multipart_snapshot,
    )


def _create_multipart_binary_request_case(client: HttpClient) -> Scenario:
    return Scenario(
        client=client,
        step_message="[POST] /api/v1/upload",
        request=client.client.build_request(
            method="POST",
            url="/api/v1/upload",
            files={
                "file": (
                    "file.bin",
                    (SRC_ROOT / "data" / "file.bin").read_bytes(),
                )
            },
        ),
        prepare_snapshot=_prepare_multipart_snapshot,
    )


def _create_urlencoded_request_case(client: HttpClient) -> Scenario:
    form_fields: dict[str, str] = {"name": "Василий", "profession": "developer"}
    return Scenario(
        client=client,
        step_message="[PATCH] /api/v3/patch",
        request=client.client.build_request(
            method="PATCH",
            url="/api/v3/patch",
            data=form_fields,
        ),
    )


def _create_json_request_with_sensitive_data(client: HttpClient) -> Scenario:
    json_payload_2: dict[str, JsonValue] = {
        "data": {
            "login": "admin",
            "password": "123123",
        },
    }
    return Scenario(
        client=client,
        step_message="[GET] /api/users/me",
        request=client.client.build_request(
            method="GET",
            url="/api/users/me",
            json=json_payload_2,
        ),
    )


def _prepare_multipart_snapshot(src: str) -> str:
    # Remove the absolute path from filename, keeping only the file name
    result = re.sub(r'filename="[^"]*/([^"]*)"', r'filename="\1"', src)

    # Replace the boundary in the header
    result = re.sub(r"boundary=[a-f0-9]{32}", "boundary=<boundary>", result)

    # Also replace the boundary in the --form section
    result = re.sub(r"--[a-f0-9]{32}", "--<boundary>", result)
    return re.sub(r"--[a-f0-9]{32}--", "--<boundary>--", result)
