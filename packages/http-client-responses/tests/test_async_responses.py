from pytest_httpx import HTTPXMock

from .assertions import assert_that
from .client import AsyncExampleClient
from .data import details_body, user, users_payload
from .endpoints import details_url, users_url
from .models import ExampleRequest


async def test_parses_body_into_schema_model(async_client: AsyncExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=users_url(15), json=users_payload(user("Margaret Hamilton")))

    response = await async_client.get_users(ExampleRequest(limit=15))

    assert_that(response.model()).has_user_names(["Margaret Hamilton"])


async def test_parses_body_with_custom_parser(async_client: AsyncExampleClient, httpx_mock: HTTPXMock) -> None:
    expected_role = "astronaut"
    httpx_mock.add_response(url=details_url(12), content=details_body(role=expected_role))

    response = await async_client.download_details(user_id=12)

    assert_that(response.parse()).is_equal_to({"role": expected_role})
