import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from assertpy import assert_that
from logging_context import HandlerOptions, LoggingContextHandler

from .matchers import assert_logs


@pytest.fixture()
def logs_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs"


@pytest.fixture()
def handler(logs_dir: Path) -> Iterator[LoggingContextHandler]:
    with LoggingContextHandler(logs_dir, "fixtures_master.log") as handler:
        handler.setFormatter(logging.Formatter("%(message)s"))
        yield handler


@pytest.fixture()
def logger(request: pytest.FixtureRequest, handler: LoggingContextHandler) -> Iterator[logging.Logger]:
    logger = logging.getLogger(f"logging-context-{cast('pytest.Item', request.node).nodeid}")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    yield logger
    logger.removeHandler(handler)


def test_writes_to_fixtures_file_while_no_test_is_bound(
    logs_dir: Path,
    logger: logging.Logger,
) -> None:
    logger.info("подключаемся к стенду")

    assert_logs(logs_dir).has_log_with_lines("fixtures_master.log", "подключаемся к стенду")


def test_writes_to_test_file_while_a_test_is_bound(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    handler.bind("test_creates_order")
    logger.info("заказ создан")

    assert_logs(logs_dir).has_log_with_lines("test_creates_order.log", "заказ создан")


def test_names_test_file_after_the_bound_test(handler: LoggingContextHandler) -> None:
    path = handler.bind("test_deletes_order")

    assert_that(path.name).is_equal_to("test_deletes_order.log")


def test_keeps_fixtures_log_across_bind_cycles(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    logger.info("до первого теста")
    handler.bind("test_alpha")
    handler.unbind()
    logger.info("между тестами")
    handler.bind("test_beta")
    handler.unbind()
    logger.info("после последнего теста")

    assert_logs(logs_dir).has_log_with_lines(
        "fixtures_master.log",
        "до первого теста",
        "между тестами",
        "после последнего теста",
    )


def test_keeps_fixtures_log_after_flushing_an_unbound_handler(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    logger.info("строка фикстуры")
    handler.bind("test_gamma")
    handler.unbind()

    handler.flush()

    assert_logs(logs_dir).has_log_with_lines("fixtures_master.log", "строка фикстуры")


def test_creates_no_files_until_something_is_logged(
    logs_dir: Path,
    handler: LoggingContextHandler,
) -> None:
    handler.flush()

    assert_logs(logs_dir).is_empty()


def test_gives_repeated_test_name_a_numeric_suffix(handler: LoggingContextHandler) -> None:
    handler.bind("test_flaky")
    handler.unbind()

    second_attempt = handler.bind("test_flaky")

    assert_that(second_attempt.name).is_equal_to("test_flaky.2.log")


def test_numbers_every_further_repetition(handler: LoggingContextHandler) -> None:
    for _ in range(2):
        handler.bind("test_retried")
        handler.unbind()

    third_attempt = handler.bind("test_retried")

    assert_that(third_attempt.name).is_equal_to("test_retried.3.log")


def test_keeps_logs_of_the_previous_attempt(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    handler.bind("test_unstable")
    logger.info("первая попытка упала")
    handler.unbind()

    handler.bind("test_unstable")
    logger.info("вторая попытка прошла")
    handler.unbind()

    assert_logs(logs_dir).has_log_with_lines("test_unstable.log", "первая попытка упала")


def test_rejects_binding_over_an_active_test(handler: LoggingContextHandler) -> None:
    handler.bind("test_outer")

    with pytest.raises(RuntimeError):
        handler.bind("test_inner")


def test_forgets_current_file_after_unbind(handler: LoggingContextHandler) -> None:
    handler.bind("test_closes")
    handler.unbind()

    assert_that(handler.current_file).is_none()


def test_survives_repeated_unbind(handler: LoggingContextHandler) -> None:
    handler.bind("test_double_unbind")
    handler.unbind()
    handler.unbind()

    assert_that(handler.current_file).is_none()


def test_keeps_written_logs_after_repeated_close(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    logger.info("записано до закрытия")

    handler.close()
    handler.close()

    assert_logs(logs_dir).has_log_with_lines("fixtures_master.log", "записано до закрытия")


def test_ignores_logging_after_close(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    logger.info("записано до закрытия")
    handler.close()

    logger.info("записано после закрытия")

    assert_logs(logs_dir).has_log_without("fixtures_master.log", "записано после закрытия")


def test_rejects_binding_after_close(handler: LoggingContextHandler) -> None:
    handler.close()

    with pytest.raises(RuntimeError):
        handler.bind("test_after_close")


def test_keeps_dangerous_test_name_inside_output_dir(handler: LoggingContextHandler) -> None:
    path = handler.bind("test_uploads[a[b]/../../outside]")

    assert_that(path.resolve().parent).is_equal_to(handler.output_dir.resolve())


def test_writes_unicode_in_utf8(
    logs_dir: Path,
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    handler.bind("test_greeting")
    logger.info("привет, мир")

    assert_logs(logs_dir).has_log_with_lines("test_greeting.log", "привет, мир")


def test_creates_log_file_unreadable_by_others(
    logs_dir: Path,
    logger: logging.Logger,
) -> None:
    logger.info("секрет стенда")

    assert_logs(logs_dir).has_log_unreadable_by_others("fixtures_master.log")


def test_creates_output_dir_unreadable_by_others(logs_dir: Path, handler: LoggingContextHandler) -> None:
    handler.bind("test_permissions")

    assert_logs(logs_dir).is_unreadable_by_others()


def test_closes_handler_on_leaving_context_manager(logs_dir: Path) -> None:
    with LoggingContextHandler(logs_dir) as handler:
        handler.bind("test_in_context")

    assert_that(handler.current_file).is_none()


def test_survives_background_logging_during_file_switching(
    handler: LoggingContextHandler,
    logger: logging.Logger,
) -> None:
    stop = threading.Event()
    failures: list[BaseException] = []

    def spam() -> None:
        try:
            while not stop.is_set():
                logger.info("сообщение из фонового потока")
        except BaseException as error:  # noqa: BLE001
            failures.append(error)

    worker = threading.Thread(target=spam)
    worker.start()
    try:
        for index in range(20):
            handler.bind(f"test_switch_{index}")
            handler.unbind()
    finally:
        stop.set()
        worker.join(timeout=5)

    assert_that(failures).described_as(
        "запись из фонового потока не должна попадать в закрытый файл при смене контекста",
    ).is_empty()


def test_options_add_worker_suffix_to_bound_filename(logs_dir: Path) -> None:
    with LoggingContextHandler(logs_dir, options=HandlerOptions(name_suffix="gw7")) as handler:
        path = handler.bind("test_worker")

    assert_that(path.name).is_equal_to("test_worker.gw7.log")
