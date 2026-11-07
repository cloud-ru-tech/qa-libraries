import httpx
from assertpy import assert_that
from httpx_curlify import to_curl
from syrupy.assertion import SnapshotAssertion


def test_to_curl_simple_get_request(snapshot: SnapshotAssertion) -> None:
    """Преобразование простого GET запроса."""
    request = httpx.Request("GET", "https://example.com/api/users")

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_post_request_with_json(snapshot: SnapshotAssertion) -> None:
    """Преобразование POST запроса с JSON телом."""
    request = httpx.Request(
        "POST",
        "https://example.com/api/users",
        json=dict[str, object]({"name": "John", "age": 30}),
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_custom_headers(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса с кастомными заголовками."""
    request = httpx.Request(
        "GET",
        "https://example.com/api/data",
        headers={
            "Authorization": "Bearer token123",
            "X-Custom-Header": "custom-value",
        },
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_empty_header_value(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса с пустым значением заголовка."""
    request = httpx.Request(
        "GET",
        "https://example.com/api/data",
        headers={"X-Empty": ""},
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_post_request_with_form_data(snapshot: SnapshotAssertion) -> None:
    """Преобразование POST запроса с form data."""
    request = httpx.Request(
        "POST",
        "https://example.com/api/form",
        data=dict[str, object]({"field1": "value1", "field2": "value2"}),
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_sanitize_keys_in_headers(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса со скрытием чувствительных данных в заголовках."""
    request = httpx.Request(
        "GET",
        "https://example.com/api/data",
        headers={
            "Authorization": "Bearer secret_token",
            "X-Api-Key": "api_key_value",
        },
    )

    result = to_curl(request, sanitize_keys=["authorization", "x-api-key"])

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_sanitize_keys_in_json(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса со скрытием чувствительных данных в JSON."""
    request = httpx.Request(
        "POST",
        "https://example.com/api/login",
        json=dict[str, object]({"username": "john", "password": "secret123"}),
    )

    result = to_curl(request, sanitize_keys=["password"])

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_nested_sanitize_keys(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса со скрытием вложенных чувствительных данных."""
    request = httpx.Request(
        "POST",
        "https://example.com/api/data",
        json=dict[str, object]({"user": {"name": "John", "password": "secret"}}),
    )

    result = to_curl(request, sanitize_keys=["user.password"])

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_json_dumps_kwargs(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса с параметрами форматирования JSON."""
    request = httpx.Request(
        "POST",
        "https://example.com/api/data",
        json=dict[str, object]({"name": "John", "age": 30}),
    )

    result = to_curl(request, json_dumps_kwargs={"indent": 2})

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_put_request(snapshot: SnapshotAssertion) -> None:
    """Преобразование PUT запроса."""
    request = httpx.Request(
        "PUT",
        "https://example.com/api/users/123",
        json=dict[str, object]({"name": "Updated Name"}),
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_delete_request(snapshot: SnapshotAssertion) -> None:
    """Преобразование DELETE запроса."""
    request = httpx.Request("DELETE", "https://example.com/api/users/123")

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_query_parameters(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса с query параметрами."""
    request = httpx.Request(
        "GET",
        "https://example.com/api/search",
        params={"q": "test query", "page": "1"},
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_binary_data(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса с бинарными данными."""
    binary_data = b"\x80\x81\x82\x83"
    request = httpx.Request(
        "POST",
        "https://example.com/api/upload",
        content=binary_data,
        headers={"Content-Type": "application/octet-stream"},
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_multiline_format(snapshot: SnapshotAssertion) -> None:
    """Проверка, что результат содержит переносы строк."""
    request = httpx.Request(
        "POST",
        "https://example.com/api/data",
        json=dict[str, object]({"key": "value"}),
        headers={"Authorization": "Bearer token"},
    )

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_to_curl_with_special_characters_in_url(snapshot: SnapshotAssertion) -> None:
    """Преобразование запроса с специальными символами в URL."""
    request = httpx.Request("GET", "https://example.com/api/search?q=test&filter=name")

    result = to_curl(request)

    assert_that(result).is_equal_to(snapshot)


def test_sanitization_preserves_request_body() -> None:
    request = httpx.Request(
        "POST", "https://example.com/private", json=dict[str, object]({"password": "keep-original"})
    )
    original = request.read()

    to_curl(request, sanitize_keys=["password"])

    assert_that(request.read()).is_equal_to(original)


def test_hides_secrets_inside_json_arrays() -> None:
    request = httpx.Request(
        "POST",
        "https://example.com/keys",
        json=dict[str, object]({"users": [dict[str, object]({"token": "array-secret"})]}),
    )

    command = to_curl(request, sanitize_keys=["users.*.token"])

    assert_that(command).contains("****").does_not_contain("array-secret")
