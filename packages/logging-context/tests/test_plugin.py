import json
import logging
from pathlib import Path

import pytest
from assertpy import assert_that

from .matchers import assert_run, run_pytest


def test_creates_nothing_until_output_dir_is_configured(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import logging

        def test_reads_catalog():
            logging.getLogger("test-logger").info("каталог прочитан")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).is_empty()


def test_creates_separate_file_per_test(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_opens_cart():
            logger.info("КОРЗИНА")

        def test_pays_order():
            logger.info("ОПЛАТА")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(2).has_logs(
        test_opens_cart="INFO - КОРЗИНА\n",
        test_pays_order="INFO - ОПЛАТА\n",
    )


def test_keeps_logs_of_other_tests_out_of_a_test_file(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_registers_user():
            logger.info("РЕГИСТРАЦИЯ")

        def test_confirms_email():
            logger.info("ПОДТВЕРЖДЕНИЕ")

        def test_resets_password():
            logger.info("СБРОС")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(3).has_log_without(
        "test_confirms_email.log",
        "РЕГИСТРАЦИЯ",
        "СБРОС",
    )


def test_captures_setup_and_teardown_of_the_test_fixtures(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.fixture
        def stand():
            logger.info("ПОДНЯЛИ СТЕНД")
            yield
            logger.info("ПОГАСИЛИ СТЕНД")

        def test_checks_health(stand):
            logger.info("ПРОВЕРКА")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(1).has_log_with_lines(
        "test_checks_health.log",
        "INFO - ПОДНЯЛИ СТЕНД",
        "INFO - ПРОВЕРКА",
        "INFO - ПОГАСИЛИ СТЕНД",
    )


def test_captures_session_fixture_setup_in_the_first_test(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.fixture(scope="session", autouse=True)
        def database():
            logger.info("БАЗА ПОДНЯТА")
            yield
            logger.info("БАЗА ПОГАШЕНА")

        def test_first_query():
            logger.info("ПЕРВЫЙ ЗАПРОС")

        def test_last_query():
            logger.info("ПОСЛЕДНИЙ ЗАПРОС")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(2).has_log_with_lines(
        "test_first_query.log",
        "INFO - БАЗА ПОДНЯТА",
        "INFO - ПЕРВЫЙ ЗАПРОС",
    )


def test_captures_session_fixture_teardown_in_the_last_test(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.fixture(scope="session", autouse=True)
        def database():
            yield
            logger.info("БАЗА ПОГАШЕНА")

        def test_first_query():
            logger.info("ПЕРВЫЙ ЗАПРОС")

        def test_last_query():
            logger.info("ПОСЛЕДНИЙ ЗАПРОС")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(2).has_log_with_lines(
        "test_last_query.log",
        "INFO - ПОСЛЕДНИЙ ЗАПРОС",
        "INFO - БАЗА ПОГАШЕНА",
    )


def test_collects_logs_made_outside_of_tests(logging_project: pytest.Pytester) -> None:
    logging_project.makeconftest(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def pytest_sessionstart(session):
            logger.info("СТАРТ СЕССИИ")

        def pytest_sessionfinish(session, exitstatus):
            logger.info("КОНЕЦ СЕССИИ")
        """,
    )
    logging_project.makepyfile("def test_counts_items(): pass")

    run = run_pytest(logging_project)

    assert_run(run).passed(1).has_log_with_lines(
        "fixtures_master.log",
        "INFO - СТАРТ СЕССИИ",
        "INFO - КОНЕЦ СЕССИИ",
    )


def test_keeps_fixtures_log_out_of_test_files(logging_project: pytest.Pytester) -> None:
    logging_project.makeconftest(
        """
        import logging

        def pytest_sessionstart(session):
            logging.getLogger("test-logger").info("СТАРТ СЕССИИ")
        """,
    )
    logging_project.makepyfile("def test_counts_items(): pass")

    run = run_pytest(logging_project)

    assert_run(run).passed(1).has_log_without("test_counts_items.log", "СТАРТ СЕССИИ")


def test_gives_each_parameter_set_its_own_file(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.mark.parametrize("city", ["Москва", "Казань"])
        def test_delivers(city):
            logger.info("город %s", city)
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(2).has_log_count(2)


def test_keeps_dangerous_parameter_inside_the_logs_dir(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.mark.parametrize("path", ["a[b]/../../outside"])
        def test_uploads(path):
            logger.info("СЕКРЕТ")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(1).wrote_no_logs_outside_logs_dir()


def test_keeps_logs_of_a_test_with_a_dangerous_parameter(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.mark.parametrize("path", ["a[b]/../../outside"])
        def test_uploads(path):
            logger.info("СЕКРЕТ")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(1).has_log_in_every_file_containing("СЕКРЕТ")


def test_keeps_logs_of_both_tests_with_the_same_name(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        class TestCatalog:
            def test_opens(self):
                logger.info("КАТАЛОГ")

        class TestBasket:
            def test_opens(self):
                logger.info("КОРЗИНА")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(2).has_logs(
        test_opens="INFO - КАТАЛОГ\n",
        **{"test_opens.2": "INFO - КОРЗИНА\n"},
    )


def test_keeps_logs_of_a_failing_test(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_charges_card():
            logger.info("ДО ПАДЕНИЯ")
            raise AssertionError("отказ банка")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).failed(1).has_log_with_lines("test_charges_card.log", "INFO - ДО ПАДЕНИЯ")


def test_keeps_logs_written_before_a_fixture_error(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        import pytest

        logger = logging.getLogger("test-logger")

        @pytest.fixture
        def broken_stand():
            logger.info("ДО ОШИБКИ ФИКСТУРЫ")
            raise RuntimeError("стенд недоступен")

        def test_reads_profile(broken_stand):
            pass
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).errored(1).has_log_containing("test_reads_profile.log", "ДО ОШИБКИ ФИКСТУРЫ")


def test_captures_third_party_loggers_by_default(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_calls_api():
            logging.getLogger("httpx").warning("ЗАПРОС УШЁЛ")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_calls_api.log", "ЗАПРОС УШЁЛ")


def test_captures_info_records_without_any_logger_setup(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_traces_flow():
            logging.getLogger("silent").info("ПОДРОБНОСТЬ")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_traces_flow.log", "ПОДРОБНОСТЬ")


def test_drops_debug_records_by_default(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_mixes_levels():
            logger.debug("СЛИШКОМ ПОДРОБНО")
            logger.info("В МЕРУ")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_mixes_levels.log", "В МЕРУ")


def test_captures_debug_records_when_level_lowered(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_level = DEBUG
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_traces_flow():
            logging.getLogger("silent").debug("ПОДРОБНОСТЬ")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_traces_flow.log", "ПОДРОБНОСТЬ")


def test_drops_records_below_the_configured_level(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_level = WARNING
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_filters_levels():
            logger.info("НЕ НУЖНО")
            logger.warning("НУЖНО")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_filters_levels.log", "НУЖНО")


def test_ignores_loggers_outside_the_configured_list(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_loggers = chosen
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_narrows_capture():
            logging.getLogger("chosen").warning("ВЗЯЛИ")
            logging.getLogger("skipped").warning("ПРОПУСТИЛИ")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_narrows_capture.log", "ВЗЯЛИ")


def test_writes_test_id_into_the_header(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        """,
    )
    pytester.makepyfile("def test_sends_invoice(): pass")

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_containing(
        "test_sends_invoice.log",
        "Запуск теста id=test_writes_test_id_into_the_header.py::test_sends_invoice",
    )


def test_writes_test_parameters_into_the_header(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        """,
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("currency", ["RUB"])
        def test_converts(currency):
            pass
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_in_every_file_containing(json.dumps(dict[str, object]({"currency": "RUB"})))


def test_reports_unserializable_parameters_as_a_setup_error(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_attach_allure = false
        """,
    )
    pytester.makepyfile(
        """
        import pytest

        cyclic = []
        cyclic.append(cyclic)

        @pytest.mark.parametrize("value", [cyclic], ids=["cyclic"])
        def test_accepts_anything(value):
            pass
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).errored(1)


def test_rejects_launch_id_pointing_outside_the_logs_dir(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_launch_id = ../../artifacts
        """,
    )
    pytester.makepyfile("def test_does_nothing(): pass")

    run = run_pytest(pytester)

    assert_run(run).was_stopped()


def test_explains_why_launch_id_is_rejected(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_launch_id = /tmp/elsewhere
        """,
    )
    pytester.makepyfile("def test_does_nothing(): pass")

    run = run_pytest(pytester)

    assert_run(run).reports_error("*must be a single path component*")


def test_puts_logs_of_a_launch_into_its_own_subdirectory(pytester: pytest.Pytester) -> None:
    launch_id = "run-2026-07-30"
    pytester.makeini(
        f"""
        [pytest]
        logging_context_dir = logs
        logging_context_launch_id = {launch_id}
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_builds_report():
            logging.getLogger("test-logger").info("отчёт собран")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).in_launch(launch_id).has_log("test_builds_report.log")


def test_takes_launch_id_from_the_command_line(logging_project: pytest.Pytester) -> None:
    launch_id = "pipeline-4821"
    logging_project.makepyfile(
        """
        import logging

        def test_builds_report():
            logging.getLogger("test-logger").info("отчёт собран")
        """,
    )

    run = run_pytest(logging_project, f"--logging-context-launch-id={launch_id}")

    assert_run(run).passed(1).in_launch(launch_id).has_log("test_builds_report.log")


def test_takes_launch_id_from_the_environment(
    logging_project: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_id = "nightly-77"
    monkeypatch.setenv("LOGGING_CONTEXT_LAUNCH_ID", launch_id)
    logging_project.makepyfile(
        """
        import logging

        def test_builds_report():
            logging.getLogger("test-logger").info("отчёт собран")
        """,
    )

    run = run_pytest(logging_project)

    assert_run(run).passed(1).in_launch(launch_id).has_log("test_builds_report.log")


def test_prefers_command_line_launch_id_over_the_environment(
    logging_project: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOGGING_CONTEXT_LAUNCH_ID", "from-env")
    logging_project.makepyfile(
        """
        import logging

        def test_builds_report():
            logging.getLogger("test-logger").info("отчёт собран")
        """,
    )

    run = run_pytest(logging_project, "--logging-context-launch-id=from-cli")

    assert_run(run).passed(1).in_launch("from-cli").has_log("test_builds_report.log")


def test_prefers_environment_launch_id_over_the_ini_file(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOGGING_CONTEXT_LAUNCH_ID", "from-env")
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_launch_id = from-ini
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_builds_report():
            logging.getLogger("test-logger").info("отчёт собран")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).in_launch("from-env").has_log("test_builds_report.log")


def test_rejects_launch_id_given_on_the_command_line(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile("def test_does_nothing(): pass")

    run = run_pytest(logging_project, "--logging-context-launch-id=../../artifacts")

    assert_run(run).reports_error("*--logging-context-launch-id*must be a single path component*")


def test_rejects_launch_id_given_in_the_environment(
    logging_project: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOGGING_CONTEXT_LAUNCH_ID", "/somewhere/else")
    logging_project.makepyfile("def test_does_nothing(): pass")

    run = run_pytest(logging_project)

    assert_run(run).reports_error("*LOGGING_CONTEXT_LAUNCH_ID*must be a single path component*")


def test_rejects_an_unknown_logging_level(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_level = ОЧЕНЬ_ГРОМКО
        """,
    )
    pytester.makepyfile("def test_does_nothing(): pass")

    run = run_pytest(pytester)

    assert_run(run).reports_error("*is not a valid logging level*")


def test_lets_conftest_replace_the_formatter(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makeconftest(
        """
        import logging

        def pytest_logging_context_configure(handler, config):
            handler.setFormatter(logging.Formatter("СВОЙ ФОРМАТ %(message)s"))
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_uses_custom_format():
            logging.getLogger("test-logger").info("сообщение")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_uses_custom_format.log", "СВОЙ ФОРМАТ сообщение")


def test_separates_logs_per_test_under_xdist(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_scans_barcode():
            logger.info("ШТРИХКОД")

        def test_prints_label():
            logger.info("ЭТИКЕТКА")

        def test_packs_box():
            logger.info("КОРОБКА")

        def test_ships_parcel():
            logger.info("ОТПРАВКА")
        """,
    )

    run = run_pytest(logging_project, "-n", "2", in_subprocess=True)

    assert_run(run).passed(4).has_test_logs(
        test_scans_barcode="INFO - ШТРИХКОД\n",
        test_prints_label="INFO - ЭТИКЕТКА\n",
        test_packs_box="INFO - КОРОБКА\n",
        test_ships_parcel="INFO - ОТПРАВКА\n",
    )


def test_gives_every_xdist_worker_its_own_fixtures_file(logging_project: pytest.Pytester) -> None:
    logging_project.makeconftest(
        """
        import logging

        def pytest_sessionstart(session):
            logging.getLogger("test-logger").info("ВОРКЕР ПОДНЯТ")
        """,
    )
    logging_project.makepyfile(
        """
        def test_reads_queue(): pass

        def test_writes_queue(): pass
        """,
    )

    run = run_pytest(logging_project, "-n", "2", in_subprocess=True)

    assert_run(run).passed(2).has_log_with_lines("fixtures_gw1.log", "INFO - ВОРКЕР ПОДНЯТ")


def test_attaches_the_test_log_to_allure(pytester: pytest.Pytester, tmp_path: Path) -> None:
    allure_dir = tmp_path / "allure-results"
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_books_ticket():
            logger.info("БРОНЬ")

        def test_cancels_ticket():
            logger.info("ОТМЕНА")
        """,
    )

    run = run_pytest(pytester, allure_dir=allure_dir)

    assert_run(run).passed(2).has_attachment("test_books_ticket", "test_books_ticket.log", "БРОНЬ\n")


def test_keeps_other_tests_out_of_an_allure_attachment(pytester: pytest.Pytester, tmp_path: Path) -> None:
    allure_dir = tmp_path / "allure-results"
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")

        def test_adds_review():
            logger.info("ОТЗЫВ")

        def test_removes_review():
            logger.info("УДАЛЕНИЕ")
        """,
    )

    run = run_pytest(pytester, allure_dir=allure_dir)

    assert_run(run).passed(2).has_attachment("test_removes_review", "test_removes_review.log", "УДАЛЕНИЕ\n")


def test_attaches_the_fixtures_log_to_every_test(pytester: pytest.Pytester, tmp_path: Path) -> None:
    allure_dir = tmp_path / "allure-results"
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_log_test_header = false
        """,
    )
    pytester.makeconftest(
        """
        import logging

        def pytest_sessionstart(session):
            logging.getLogger("test-logger").info("ОБЩАЯ ПОДГОТОВКА")
        """,
    )
    pytester.makepyfile(
        """
        def test_lists_orders(): pass

        def test_filters_orders(): pass
        """,
    )

    run = run_pytest(pytester, allure_dir=allure_dir)

    assert_run(run).passed(2).has_attachment_for_every_test("fixtures_master.log", "ОБЩАЯ ПОДГОТОВКА\n")


def test_can_stop_attaching_the_fixtures_log(pytester: pytest.Pytester, tmp_path: Path) -> None:
    allure_dir = tmp_path / "allure-results"
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_attach_fixtures_log = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makeconftest(
        """
        import logging

        def pytest_sessionstart(session):
            logging.getLogger("test-logger").info("ОБЩАЯ ПОДГОТОВКА")
        """,
    )
    pytester.makepyfile("def test_exports_orders(): pass")

    run = run_pytest(pytester, allure_dir=allure_dir)

    assert_run(run).passed(1).has_no_attachment("test_exports_orders", "fixtures_master.log")


def test_can_stop_attaching_logs_to_allure(pytester: pytest.Pytester, tmp_path: Path) -> None:
    allure_dir = tmp_path / "allure-results"
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_prints_receipt():
            logging.getLogger("test-logger").info("ЧЕК")
        """,
    )

    run = run_pytest(pytester, allure_dir=allure_dir)

    assert_run(run).passed(1).has_no_attachment("test_prints_receipt", "test_prints_receipt.log")


def test_keeps_logs_of_same_named_tests_on_different_xdist_workers(
    logging_project: pytest.Pytester,
) -> None:
    logging_project.makepyfile(
        test_catalog="""
        import logging

        class TestCatalog:
            def test_opens(self):
                logging.getLogger("test-logger").info("КАТАЛОГ")
        """,
        test_basket="""
        import logging

        class TestBasket:
            def test_opens(self):
                logging.getLogger("test-logger").info("КОРЗИНА")
        """,
    )

    run = run_pytest(logging_project, "-n", "2", in_subprocess=True)

    assert_run(run).passed(2).has_log_count(2)


def test_names_test_files_per_worker_under_xdist(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        def test_reads_queue():
            logging.getLogger("test-logger").info("ОЧЕРЕДЬ")
        """,
    )

    run = run_pytest(logging_project, "-n", "1", in_subprocess=True)

    assert_run(run).passed(1).has_log_with_lines("test_reads_queue.gw0.log", "INFO - ОЧЕРЕДЬ")


def test_captures_logger_that_stops_propagating_after_startup(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        late = logging.getLogger("late.logger")
        late.propagate = False

        def test_logs():
            late.info("ЗАПИСЬ ПОЗДНЕГО ЛОГГЕРА")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_logs.log", "ЗАПИСЬ ПОЗДНЕГО ЛОГГЕРА")


def test_gives_every_rerun_attempt_its_own_file(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile(
        """
        import logging

        logger = logging.getLogger("test-logger")
        attempts = []

        def test_flaky():
            attempts.append(1)
            logger.info("ПОПЫТКА %s", len(attempts))
            if len(attempts) < 3:
                raise AssertionError("падаем специально")
        """,
    )

    run = run_pytest(logging_project, "--reruns", "2")

    assert_run(run).passed(1).has_logs(
        test_flaky="INFO - ПОПЫТКА 1\n",
        **{"test_flaky.2": "INFO - ПОПЫТКА 2\n", "test_flaky.3": "INFO - ПОПЫТКА 3\n"},
    )


def test_writes_a_record_once_for_nested_logger_names(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_loggers = app app.http
        logging_context_format = %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makepyfile(
        """
        import logging

        def test_calls_api():
            logging.getLogger("app.http").info("ОДНА СТРОКА")
        """,
    )

    run = run_pytest(pytester)

    assert_run(run).passed(1).has_log_with_lines("test_calls_api.log", "ОДНА СТРОКА")


def test_restores_logger_level_after_the_run(pytester: pytest.Pytester) -> None:
    root = logging.getLogger()
    level_before = root.level
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_level = DEBUG
        logging_context_attach_allure = false
        """,
    )
    pytester.makepyfile("def test_does_nothing(): pass")

    run_pytest(pytester)

    assert_that(root.level).described_as("плагин не должен оставлять уровень логгера пониженным").is_equal_to(
        level_before,
    )


def test_rejects_launch_id_with_a_windows_drive(logging_project: pytest.Pytester) -> None:
    logging_project.makepyfile("def test_does_nothing(): pass")

    run = run_pytest(logging_project, "--logging-context-launch-id=D:run")

    assert_run(run).reports_error("*must be a single path component*")
