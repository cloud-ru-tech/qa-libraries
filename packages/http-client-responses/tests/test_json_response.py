from datetime import datetime

import pytest
from http_client_responses import ResponseParseError
from httpx import HTTPStatusError
from pydantic import ValidationError
from pytest_httpx import HTTPXMock

from .assertions import assert_that
from .client import ExampleClient
from .data import user, users_payload
from .endpoints import users_url
from .models import ExampleRequest


def test_parses_body_into_schema_model(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=users_url(), json=users_payload(user("Grace Hopper"), user("Alan Turing")))

    response = client.get_users(ExampleRequest())

    assert_that(response.model()).has_user_names(["Grace Hopper", "Alan Turing"])


def test_parses_total_from_body(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    expected_total = 137
    httpx_mock.add_response(url=users_url(20, 40), json=dict[str, object]({"users": [], "total": expected_total}))

    response = client.get_users(ExampleRequest(limit=20, offset=40))

    assert_that(response.model().total).is_equal_to(expected_total)


def test_parses_nested_user_skills(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    expected_skills = ["Rust", "Kubernetes"]
    httpx_mock.add_response(url=users_url(5), json=users_payload(user("Ada Lovelace", skills=expected_skills)))

    response = client.get_users(ExampleRequest(limit=5))

    assert_that(response.model()).has_skills({"Ada Lovelace": expected_skills})


def test_parses_user_timestamps(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    expected_moment = datetime(1939, 11, 7, 3, 15)  # noqa: DTZ001
    payload = users_payload(user("Barbara Liskov", created_at=expected_moment.isoformat()))
    httpx_mock.add_response(url=users_url(1, 2), json=payload)

    response = client.get_users(ExampleRequest(limit=1, offset=2))

    assert_that(response.model().users[0].created_at).is_equal_to(expected_moment)


def test_reuses_parsed_model(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=users_url(7), json=users_payload(user("Katherine Johnson")))
    response = client.get_users(ExampleRequest(limit=7))
    first = response.model()

    second = response.model()

    assert_that(second).is_same_as(first)


def test_returns_itself_from_raise_for_status(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=users_url(3), json=users_payload())

    response = client.get_users(ExampleRequest(limit=3))

    assert_that(response.raise_for_status()).is_same_as(response)


def test_raises_status_error_on_server_error(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=users_url(50), status_code=503, json=dict[str, object]({"detail": "unavailable"}))
    response = client.get_users(ExampleRequest(limit=50))

    with pytest.raises(HTTPStatusError):
        response.raise_for_status()


def test_reports_request_when_body_does_not_match_schema(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    url = users_url(2)
    httpx_mock.add_response(url=url, json=dict[str, object]({"users": [], "total": "много"}))
    response = client.get_users(ExampleRequest(limit=2))

    with pytest.raises(ResponseParseError) as error:
        response.model()

    assert_that(error.value).reports_request("GET", url, 200)


def test_quotes_body_when_body_does_not_match_schema(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    unparsable_total = "восемьдесят восемь"
    httpx_mock.add_response(url=users_url(9), json=dict[str, object]({"users": [], "total": unparsable_total}))
    response = client.get_users(ExampleRequest(limit=9))

    with pytest.raises(ResponseParseError) as error:
        response.model()

    assert_that(error.value).quotes_body(unparsable_total)


def test_keeps_validation_error_as_cause(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=users_url(4), json=dict[str, object]({"users": [{"name": "Nobody"}], "total": 1}))
    response = client.get_users(ExampleRequest(limit=4))

    with pytest.raises(ResponseParseError) as error:
        response.model()

    assert_that(error.value).caused_by(ValidationError)
