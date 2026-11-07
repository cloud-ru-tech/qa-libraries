from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps
from httpx import codes

from .config import BASE_URL, SRC_ROOT

JSON_SAMPLE_CONTENT = {
    "data": [
        {
            "id": "0f75c97f-1926-4bf3-8c0d-98a1e5beb40f",
            "name": "Alexandr",
            "age": 30,
            "address": None,
            "password": "123456",
        },
        {
            "id": "1c14009c-1384-496f-b3dc-6d34d28de3bd",
            "name": "Aleksey",
            "age": 25,
            "address": "Санкт-Петербург",
            "password": "654321",
        },
    ]
}


class ResponseParams(TypedDict, total=False):
    status_code: int
    text: str
    json: object
    content: bytes


@dataclass(slots=True)
class Scenario:
    client: HttpClient
    response_params: ResponseParams


def case_response_with_text_body() -> Scenario:
    return Scenario(
        client=HttpClient(BASE_URL, wrap_requests_and_responses_in_steps()),
        response_params={
            "status_code": codes.OK,
            "text": "Hello, world!",
        },
    )


def case_response_with_json_body() -> Scenario:
    return Scenario(
        client=HttpClient(BASE_URL, wrap_requests_and_responses_in_steps()),
        response_params={
            "status_code": codes.OK,
            "json": JSON_SAMPLE_CONTENT,
        },
    )


def case_response_with_formatted_json_body() -> Scenario:
    return Scenario(
        client=HttpClient(
            BASE_URL,
            wrap_requests_and_responses_in_steps(json_dumps_kwargs={"indent": 2}),
        ),
        response_params={
            "status_code": codes.OK,
            "json": JSON_SAMPLE_CONTENT,
        },
    )


def case_response_with_sensitive_data_in_json_body() -> Scenario:
    return Scenario(
        client=HttpClient(
            BASE_URL,
            wrap_requests_and_responses_in_steps(sanitize_keys=["data.*.password"]),
        ),
        response_params={
            "status_code": codes.OK,
            "json": JSON_SAMPLE_CONTENT,
        },
    )


def case_response_with_binary_body() -> Scenario:
    binary_file = Path(SRC_ROOT / "data" / "file.bin")
    return Scenario(
        client=HttpClient(BASE_URL, wrap_requests_and_responses_in_steps()),
        response_params={
            "status_code": codes.OK,
            "content": binary_file.read_bytes(),
        },
    )
