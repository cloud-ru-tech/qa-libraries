import asyncio
from typing import TYPE_CHECKING

import httpx
import pytest
from assertpy import assert_that
from http_client import AsyncHttpClient
from http_client_allure import wrap_requests_and_responses_in_steps
from pytest_httpx import HTTPXMock

from .allure_recorder import Report
from .assertions import assert_attachment

if TYPE_CHECKING:
    from .json_types import JsonValue

# Completion follows start order rather than reversing it: reverse
# order hides attachments assigned to the wrong step and the test catches nothing.
DELAYS = {"/fast": 0.01, "/medium": 0.03, "/slow": 0.05}


@pytest.fixture()
def delayed_responses(httpx_mock: HTTPXMock) -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(DELAYS[request.url.path])
        json_payload_1: dict[str, JsonValue] = {"path": request.url.path}
        return httpx.Response(200, json=json_payload_1)

    httpx_mock.add_callback(respond, is_reusable=True)


@pytest.mark.usefixtures("delayed_responses")
async def test_keeps_response_with_its_own_step(report: Report) -> None:
    async with AsyncHttpClient("https://parallel.test", wrap_requests_and_responses_in_steps()) as client:
        await asyncio.gather(client.get("/fast"), client.get("/medium"), client.get("/slow"))

    step = next(step for step in report.steps if step.title == "[GET] /slow")
    assert_attachment(step.attachments[-1]).has_json_value("path", "/slow")


@pytest.mark.usefixtures("delayed_responses")
async def test_keeps_request_with_its_own_step(report: Report) -> None:
    async with AsyncHttpClient("https://parallel.test", wrap_requests_and_responses_in_steps()) as client:
        await asyncio.gather(client.get("/fast"), client.get("/medium"), client.get("/slow"))

    step = next(step for step in report.steps if step.title == "[GET] /fast")
    assert_attachment(step.attachments[0]).has_json_value("url", "https://parallel.test/fast")


@pytest.mark.usefixtures("delayed_responses")
async def test_does_not_nest_concurrent_steps(report: Report) -> None:
    async with AsyncHttpClient("https://parallel.test", wrap_requests_and_responses_in_steps()) as client:
        await asyncio.gather(client.get("/fast"), client.get("/medium"), client.get("/slow"))

    assert_that(len(report.steps), "каждый параллельный запрос должен получить собственный шаг").is_equal_to(3)
