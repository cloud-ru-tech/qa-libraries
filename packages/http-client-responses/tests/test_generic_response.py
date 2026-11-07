import pytest
from http_client_responses import GenericResponse, ResponseParseError
from httpx import Response
from pytest_httpx import HTTPXMock

from .assertions import assert_that
from .client import ExampleClient
from .data import details_body
from .endpoints import details_url

UNPARSABLE_BODY = b"there is no separator in this line"


def test_parses_body_with_custom_parser(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    expected_email = "grace@navy.mil"
    httpx_mock.add_response(url=details_url(7), content=details_body(email=expected_email))

    response = client.download_details(user_id=7)

    assert_that(response.parse()).is_equal_to({"email": expected_email})


def test_strips_whitespace_around_parsed_values(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=details_url(23), content=b"role:    lead engineer   ")

    response = client.download_details(user_id=23)

    assert_that(response.parse()).is_equal_to({"role": "lead engineer"})


def test_reuses_parsed_result(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=details_url(3), content=details_body(city="Amsterdam"))
    response = client.download_details(user_id=3)
    first = response.parse()

    second = response.parse()

    assert_that(second).is_same_as(first)


def test_reports_request_when_parser_fails(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    url = details_url(11)
    httpx_mock.add_response(url=url, content=UNPARSABLE_BODY)
    response = client.download_details(user_id=11)

    with pytest.raises(ResponseParseError) as error:
        response.parse()

    assert_that(error.value).reports_request("GET", url, 200)


def test_quotes_body_when_parser_fails(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=details_url(4), content=UNPARSABLE_BODY)
    response = client.download_details(user_id=4)

    with pytest.raises(ResponseParseError) as error:
        response.parse()

    assert_that(error.value).quotes_body(UNPARSABLE_BODY.decode())


def test_keeps_parser_error_as_cause(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=details_url(19), content=UNPARSABLE_BODY)
    response = client.download_details(user_id=19)

    with pytest.raises(ResponseParseError) as error:
        response.parse()

    assert_that(error.value).caused_by(ValueError)


def test_omits_oversized_body_from_error_message(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    oversized_body = "z" * (ResponseParseError.BODY_PREVIEW_LIMIT * 3)
    httpx_mock.add_response(url=details_url(64), content=oversized_body.encode())
    response = client.download_details(user_id=64)

    with pytest.raises(ResponseParseError) as error:
        response.parse()

    assert_that(error.value).omits_body(oversized_body)


def test_keeps_body_prefix_in_error_message(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    oversized_body = "q" * (ResponseParseError.BODY_PREVIEW_LIMIT * 3)
    httpx_mock.add_response(url=details_url(65), content=oversized_body.encode())
    response = client.download_details(user_id=65)

    with pytest.raises(ResponseParseError) as error:
        response.parse()

    assert_that(error.value).quotes_body(oversized_body[: ResponseParseError.BODY_PREVIEW_LIMIT])


def test_keeps_whole_multibyte_characters_in_error_message(client: ExampleClient, httpx_mock: HTTPXMock) -> None:
    char = "€"
    chars_within_limit = ResponseParseError.BODY_PREVIEW_LIMIT // len(char.encode())
    httpx_mock.add_response(url=details_url(77), content=(char * 1000).encode())
    response = client.download_details(user_id=77)

    with pytest.raises(ResponseParseError) as error:
        response.parse()

    assert_that(error.value).quotes_body(char * chars_within_limit)


def test_caches_none_returned_by_custom_parser() -> None:
    calls: list[int] = []

    def parse(_response: Response) -> None:
        calls.append(1)

    wrapper = GenericResponse(Response(204), parse)
    wrapper.parse()
    wrapper.parse()

    assert_that(calls).is_equal_to([1])
