import pytest
from http_client_responses import ResponseParseError, ResponseWrapper
from httpx import HTTPStatusError, Request, Response

from .assertions import assert_that


def test_keeps_repeated_headers() -> None:
    response = Response(200, headers=[("set-cookie", "session=abc"), ("set-cookie", "theme=dark")])

    wrapper = ResponseWrapper(response)

    assert_that(wrapper.headers.get_list("set-cookie")).is_equal_to(["session=abc", "theme=dark"])


def test_joins_repeated_headers_in_raw_headers() -> None:
    response = Response(200, headers=[("x-trace", "one"), ("x-trace", "two")])

    wrapper = ResponseWrapper(response)

    assert_that(wrapper.raw_headers["x-trace"]).is_equal_to("one, two")


def test_looks_up_headers_case_insensitively() -> None:
    expected_type = "application/xml"
    response = Response(200, headers={"Content-Type": expected_type})

    wrapper = ResponseWrapper(response)

    assert_that(wrapper.headers["CONTENT-TYPE"]).is_equal_to(expected_type)


def test_shows_method_url_and_status_in_repr() -> None:
    response = Response(404, request=Request("DELETE", "http://api.local/items/8"))

    wrapper = ResponseWrapper(response)

    assert_that(repr(wrapper)).is_equal_to("<ResponseWrapper DELETE http://api.local/items/8 -> 404>")


def test_builds_repr_without_request() -> None:
    wrapper = ResponseWrapper(Response(204))

    assert_that(repr(wrapper)).is_equal_to("<ResponseWrapper ? ? -> 204>")


def test_marks_4xx_as_client_error() -> None:
    wrapper = ResponseWrapper(Response(422))

    assert_that(wrapper.is_client_error).is_true()


def test_marks_5xx_as_server_error() -> None:
    wrapper = ResponseWrapper(Response(502))

    assert_that(wrapper.is_server_error).is_true()


def test_marks_4xx_as_unsuccessful() -> None:
    wrapper = ResponseWrapper(Response(418))

    assert_that(wrapper.is_success).is_false()


def test_raises_status_error_on_unfollowed_redirect() -> None:
    request = Request("GET", "http://api.local/old")
    wrapper = ResponseWrapper(Response(302, request=request, headers={"location": "/new"}))

    with pytest.raises(HTTPStatusError):
        wrapper.raise_for_status()


def test_raises_status_error_on_informational_status() -> None:
    wrapper = ResponseWrapper(Response(100, request=Request("GET", "http://api.local/upload")))

    with pytest.raises(HTTPStatusError):
        wrapper.raise_for_status()


def test_raises_runtime_error_from_raise_for_status_without_request() -> None:
    wrapper = ResponseWrapper(Response(500))

    with pytest.raises(RuntimeError):
        wrapper.raise_for_status()


def test_parses_json_body() -> None:
    expected_body = {"status": "ok", "queued": 4}
    wrapper = ResponseWrapper(Response(200, json=expected_body))

    assert_that(wrapper.json()).is_equal_to(expected_body)


def test_reports_request_when_body_is_not_json() -> None:
    url = "http://api.local/health"
    wrapper = ResponseWrapper(Response(200, request=Request("GET", url), content=b"<html>oops</html>"))

    with pytest.raises(ResponseParseError) as error:
        wrapper.json()

    assert_that(error.value).reports_request("GET", url, 200)


def test_marks_unread_streamed_body_in_error_message() -> None:
    request = Request("GET", "http://api.local/events")
    wrapper = ResponseWrapper(Response(200, request=request, content=iter([b"chunk"])))

    with pytest.raises(ResponseParseError) as error:
        wrapper.json()

    assert_that(error.value).quotes_body("<streamed content>")
