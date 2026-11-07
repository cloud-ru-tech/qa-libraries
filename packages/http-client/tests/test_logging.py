import logging
from contextlib import closing
from typing import cast

import pytest
from http_client.config import DEFAULT_OCTET_STREAM_LOG_MAXLENGTH, LoggingConfig, configure_logging
from http_client.options import with_logger
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory
from .support.logs import RecordedLog, assert_that


@pytest.fixture(params=("object", "array"))
def nested_secret_payload(request: pytest.FixtureRequest) -> tuple[object, str]:
    if cast("str", request.param) == "object":
        return (
            {"profile": {"username": "olga", "password": "nested-secret-911"}, "items": [{"access_token": "token-83"}]},
            '{"profile": {"username": "olga", "password": "****"}, "items": [{"access_token": "****"}]}',
        )
    return (
        [{"credentials": {"token": "list-secret-821"}, "id": 47}, {"api_key": "array-key-509", "active": False}],
        '[{"credentials": {"token": "****"}, "id": 47}, {"api_key": "****", "active": false}]',
    )


def test_masks_nested_default_secrets_in_request_log(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
    nested_secret_payload: tuple[object, str],
) -> None:
    payload, expected = nested_secret_payload
    httpx_mock.add_response()
    client = new_client("https://accounts.test", with_logger(recorded_log.logger))

    client.post("/profiles", json=payload)

    assert_that(recorded_log.request).has_body(expected)


def test_masks_nested_default_secrets_in_response_log(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
    nested_secret_payload: tuple[object, str],
) -> None:
    payload, expected = nested_secret_payload
    httpx_mock.add_response(json=payload)
    client = new_client("https://tokens.test", with_logger(recorded_log.logger))

    client.get("/credentials")

    assert_that(recorded_log.response).has_body(expected)


async def test_masks_nested_default_secrets_in_async_request_log(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
    nested_secret_payload: tuple[object, str],
) -> None:
    payload, expected = nested_secret_payload
    httpx_mock.add_response()
    client = new_async_client("https://profiles.test", with_logger(recorded_log.logger))

    await client.post("/settings", json=payload)

    assert_that(recorded_log.request).has_body(expected)


async def test_masks_nested_default_secrets_in_async_response_log(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
    nested_secret_payload: tuple[object, str],
) -> None:
    payload, expected = nested_secret_payload
    httpx_mock.add_response(json=payload)
    client = new_async_client("https://sessions.test", with_logger(recorded_log.logger))

    await client.get("/identity")

    assert_that(recorded_log.response).has_body(expected)


def test_preserves_nested_values_when_default_masking_is_disabled(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    httpx_mock.add_response()
    client = new_client("https://masking.test", with_logger(recorded_log.logger, use_default_sanitize_keys=False))

    client.post("/diagnostics", json={"nested": {"password": "explicitly-visible"}})

    assert_that(recorded_log.request).has_body('{"nested": {"password": "explicitly-visible"}}')


def test_logs_request_trace_id(recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Лог запроса начинается с идентификатора обмена."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.request).has_trace_id()


def test_response_repeats_request_trace_id(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Лог ответа несёт тот же идентификатор обмена, что и лог запроса."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).has_same_trace_id_as(recorded_log.request)


def test_logs_request_method_and_url(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """В лог запроса попадают метод и адрес."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://shop.example.com", with_logger(recorded_log.logger))

    client.get("/api/orders")

    assert_that(recorded_log.request).describes_request("GET", "https://shop.example.com/api/orders")


def test_logs_request_headers(recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """В лог запроса попадают его заголовки."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test", headers={"X-Correlation-Id": "abc-42"})

    assert_that(recorded_log.request).has_header("x-correlation-id", "abc-42")


def test_logs_query_params(recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """В лог запроса попадают параметры строки запроса."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/search", params={"q": "kittens"})

    assert_that(recorded_log.request).has_query_param("q", "kittens")


def test_masks_secret_query_param(
    recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Типовой секрет в строке запроса маскируется."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/search", params={"token": "qp-secret-value"})

    assert_that(recorded_log.request).hides("qp-secret-value")


def test_masks_authorization_header_by_default(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Заголовок авторизации маскируется, даже если sanitize_keys не задан."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test", headers={"Authorization": "Bearer eyJhbGciOi"})

    assert_that(recorded_log.request).hides("Bearer eyJhbGciOi")


def test_replaces_masked_header_with_stars(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """На месте замаскированного заголовка остаётся заглушка."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test", headers={"Authorization": "Bearer eyJhbGciOi"})

    assert_that(recorded_log.request).has_header("authorization", "****")


def test_masks_api_key_header_by_default(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Ключ API маскируется, даже если sanitize_keys не задан."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test", headers={"X-Api-Key": "ak-9f3c1"})

    assert_that(recorded_log.request).hides("ak-9f3c1")


def test_masks_password_in_json_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Пароль в теле запроса маскируется."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/api/login", json={"username": "ivan", "password": "hunter2"})

    assert_that(recorded_log.request).hides("hunter2")


def test_masks_access_token_in_json_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Токен доступа в теле запроса маскируется."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/api/refresh", json={"access_token": "at-77123"})

    assert_that(recorded_log.request).hides("at-77123")


def test_masks_key_listed_in_sanitize_keys(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Маскируется и ключ, перечисленный вызывающим кодом."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger, sanitize_keys=["card.number"]))

    client.post("/api/pay", json={"card": {"number": "4111111111111111"}})

    assert_that(recorded_log.request).hides("4111111111111111")


def test_keeps_non_secret_data_in_json_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Несекретные поля тела остаются в логе как есть."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/api/login", json={"username": "ivan", "password": "hunter2"})

    assert_that(recorded_log.request).has_body('{"username": "ivan", "password": "****"}')


def test_default_masking_can_be_disabled(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Маскирование по умолчанию отключается явным флагом."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger, use_default_sanitize_keys=False))

    client.get("/api/test", headers={"Authorization": "Bearer visible"})

    assert_that(recorded_log.request).reveals("Bearer visible")


def test_logs_response_status(recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """В лог ответа попадают код и его расшифровка."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).describes_response(200, "OK")


def test_logs_error_response_status(
    recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Ответ с ошибкой логируется так же, как успешный."""
    httpx_mock.add_response(status_code=404)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/non-existent")

    assert_that(recorded_log.response).describes_response(404, "Not Found")


def test_logs_response_headers(recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """В лог ответа попадают его заголовки."""
    httpx_mock.add_response(status_code=200, headers={"X-Ratelimit-Remaining": "97"})
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).has_header("x-ratelimit-remaining", "97")


def test_logs_json_response_body(
    recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Тело JSON-ответа попадает в лог."""
    payload: dict[str, str] = {"status": "success"}
    httpx_mock.add_response(status_code=200, json=payload)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).has_body('{"status": "success"}')


def test_logs_error_response_body(
    recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Тело ответа с ошибкой попадает в лог."""
    payload: dict[str, str] = {"message": "Not found"}
    httpx_mock.add_response(status_code=404, json=payload)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/non-existent")

    assert_that(recorded_log.response).has_body('{"message": "Not found"}')


def test_logs_plain_text_response_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Тело ответа с Content-Type: text/plain попадает в лог.

    Регрессия: условие проверяло перевёрнутый MIME-тип "plain/text",
    поэтому текстовые тела в лог не попадали никогда.
    """
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "text/plain"}, content=b"Hello, world!")
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/text")

    assert_that(recorded_log.response).has_body("Hello, world!")


def test_decodes_body_with_declared_charset(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Тело декодируется кодировкой из Content-Type, а не всегда utf-8."""
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "text/plain; charset=iso-8859-1"},
        content="café".encode("iso-8859-1"),
    )
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/text")

    assert_that(recorded_log.response).has_body("café")


def test_decodes_body_with_charset_among_other_parameters(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Кодировка выбирается по имени параметра, а не по остатку строки после charset=.

    Регрессия: у Content-Type с несколькими параметрами кодировкой считалось
    "iso-8859-1; format=flowed", и тело попадало в лог как <Error parse: LookupError>.
    """
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "text/plain; charset=iso-8859-1; format=flowed"},
        content="café".encode("iso-8859-1"),
    )
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/text")

    assert_that(recorded_log.response).has_body("café")


def test_falls_back_to_utf8_for_unknown_charset(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Неизвестное имя кодировки не должно прятать тело."""
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "text/plain; charset=totally-unknown"},
        content="привет".encode(),
    )
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/text")

    assert_that(recorded_log.response).has_body("привет")


def test_marks_unsupported_content_type(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Тело неподдерживаемого типа явно помечается как непрологированное."""
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "application/xml"}, content=b"<a/>")
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).has_body("<not logged, content-type: application/xml>")


def test_marks_undecodable_octet_stream_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Двоичное тело в лог не попадает, вместо него остаётся его размер."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/binary", content=b"\xff\xfe\x00\x01", headers={"Content-Type": "application/octet-stream"})

    assert_that(recorded_log.request).has_body("<binary content (4 bytes)>")


def test_omits_body_when_request_has_no_content_type(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Запрос без тела не получает в логе строку Body."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.request).has_no_body()


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 10, 40])
def test_never_logs_body_longer_than_limit(
    limit: int,
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Обрезка никогда не отдаёт в лог тело длиннее лимита.

    Регрессия: при лимите меньше пяти символов обрезка выдавала строку
    длиннее исходной и дублировала содержимое.
    """
    httpx_mock.add_response(status_code=200)
    configure_logging(options=LoggingConfig(octet_stream_log_maxlength=limit))
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/binary", content=b"SECRET-DATA", headers={"Content-Type": "application/octet-stream"})

    assert_that(recorded_log.request).has_body_no_longer_than(limit)


def test_keeps_head_and_tail_of_trimmed_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Обрезанное тело сохраняет начало и конец содержимого."""
    payload = "x" * DEFAULT_OCTET_STREAM_LOG_MAXLENGTH + "y" * DEFAULT_OCTET_STREAM_LOG_MAXLENGTH
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/binary", content=payload.encode(), headers={"Content-Type": "application/octet-stream"})

    assert_that(recorded_log.request).has_body_matching(r"x+\.\.\.y+")


def test_logs_whole_body_without_limit(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Без лимита тело попадает в лог целиком."""
    payload = "payload-that-is-never-trimmed"
    httpx_mock.add_response(status_code=200)
    configure_logging(options=LoggingConfig(octet_stream_log_maxlength=None))
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/binary", content=payload.encode(), headers={"Content-Type": "application/octet-stream"})

    assert_that(recorded_log.request).has_body(payload)


def test_formats_request_body_with_indent(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Заданный отступ применяется к телу запроса."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger, json_indent=4, use_line_breaks=True))

    client.post("/api/test", json={"request": "data"})

    assert_that(recorded_log.request).has_body('{\n    "request": "data"\n}')


def test_formats_response_body_with_indent(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Заданный отступ применяется к телу ответа."""
    payload: dict[str, dict[str, str]] = {"nested": {"deep": "value"}}
    httpx_mock.add_response(status_code=200, json=payload)
    client = new_client("https://example.com", with_logger(recorded_log.logger, json_indent=2, use_line_breaks=True))

    client.get("/api/test")

    assert_that(recorded_log.response).has_body('{\n  "nested": {\n    "deep": "value"\n  }\n}')


def test_logs_at_level_given_to_logger_option(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Уровень лога берётся из опции клиента."""
    httpx_mock.add_response(status_code=200)
    client = new_client("https://example.com", with_logger(recorded_log.logger, log_level=logging.WARNING))

    client.get("/api/test")

    assert_that(recorded_log.request).logged_at(logging.WARNING)


def test_logs_request_at_globally_configured_level(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Без уровня в опции запрос логируется на глобально настроенном уровне."""
    httpx_mock.add_response(status_code=200)
    configure_logging(options=LoggingConfig(log_level=logging.DEBUG))
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.request).logged_at(logging.DEBUG)


def test_logs_response_at_globally_configured_level(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Без уровня в опции ответ логируется на глобально настроенном уровне."""
    httpx_mock.add_response(status_code=200)
    configure_logging(options=LoggingConfig(log_level=logging.DEBUG))
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).logged_at(logging.DEBUG)


def test_applies_globally_configured_indent(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Отступ применяется и когда задан глобально, а не в опции клиента."""
    httpx_mock.add_response(status_code=200)
    configure_logging(options=LoggingConfig(json_indent=4, use_line_breaks=True))
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.post("/api/test", json={"request": "data"})

    assert_that(recorded_log.request).has_body('{\n    "request": "data"\n}')


def test_reports_parse_error_kind(
    recorded_log: RecordedLog, httpx_mock: HTTPXMock, new_client: SyncClientFactory
) -> None:
    """Неразобранное тело помечается видом ошибки разбора."""
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        content=b'{"token": "SECRET-VALUE"',
    )
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).has_body("<Error parse: JSONDecodeError>")


def test_parse_error_does_not_leak_content(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Сообщение об ошибке разбора не переносит содержимое тела в лог."""
    httpx_mock.add_response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        content=b'{"token": "SECRET-VALUE"',
    )
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    client.get("/api/test")

    assert_that(recorded_log.response).hides("SECRET-VALUE")


def test_does_not_read_streamed_send(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """send(stream=True) не вычитывается логгером.

    Регрессия: маркер is_streaming ставился только в stream_request,
    поэтому логгер выгребал поток целиком до возврата вызывающему коду.
    """
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "text/plain"}, content=b"x" * 64)
    client = new_client("https://example.com", with_logger(recorded_log.logger))
    request = client.client.build_request("GET", "/api/data")

    with closing(client.send(request, stream=True)):
        pass

    assert_that(recorded_log.response).has_body("<streamed content>")


def test_does_not_read_stream_request(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Потоковый ответ stream_request тоже не вычитывается логгером."""
    payload: dict[str, str] = {"data": "value"}
    httpx_mock.add_response(status_code=200, json=payload)
    client = new_client("https://example.com", with_logger(recorded_log.logger))

    with client.stream("GET", "/stream"):
        pass

    assert_that(recorded_log.response).has_body("<streamed content>")


def test_logs_stream_request_method_and_url(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Потоковый запрос логируется так же, как обычный."""
    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_client("https://feed.example.com", with_logger(recorded_log.logger))

    with client.stream("GET", "/events") as response:
        response.read()

    assert_that(recorded_log.request).describes_request("GET", "https://feed.example.com/events")


async def test_logs_async_request_method_and_url(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Запрос асинхронного клиента логируется так же, как синхронного."""
    httpx_mock.add_response(status_code=200)
    client = new_async_client("https://async.example.com", with_logger(recorded_log.logger))

    await client.get("/api/test")

    assert_that(recorded_log.request).describes_request("GET", "https://async.example.com/api/test")


async def test_logs_async_json_response_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Тело JSON-ответа асинхронного клиента попадает в лог.

    Регрессия: response hook срабатывает до того, как httpx дочитал ответ,
    поэтому синхронный read() на асинхронном потоке давал <Error parse: ...>.
    """
    payload: dict[str, str] = {"status": "ok"}
    httpx_mock.add_response(status_code=200, json=payload)
    client = new_async_client("https://example.com", with_logger(recorded_log.logger))

    await client.get("/api/test")

    assert_that(recorded_log.response).has_body('{"status": "ok"}')


async def test_logs_async_text_response_body(
    recorded_log: RecordedLog,
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Тело текстового ответа асинхронного клиента попадает в лог."""
    httpx_mock.add_response(status_code=200, headers={"Content-Type": "text/plain"}, content=b"hello")
    client = new_async_client("https://example.com", with_logger(recorded_log.logger))

    await client.get("/api/test")

    assert_that(recorded_log.response).has_body("hello")
