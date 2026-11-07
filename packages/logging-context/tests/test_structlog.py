import pytest

from .matchers import assert_run, run_pytest

STRUCTLOG_CONFTEST = """
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def pytest_logging_context_configure(handler, config):
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(ensure_ascii=False),
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
            ],
        ),
    )
"""


@pytest.fixture()
def structlog_project(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_log_test_header = false
        logging_context_attach_allure = false
        """,
    )
    pytester.makeconftest(STRUCTLOG_CONFTEST)
    return pytester


def test_writes_structlog_events_into_the_test_file(structlog_project: pytest.Pytester) -> None:
    structlog_project.makepyfile(
        """
        import structlog

        log = structlog.get_logger("test-logger")

        def test_creates_shipment():
            log.info("отправление создано", shipment_id=77)
        """,
    )

    run = run_pytest(structlog_project)

    assert_run(run).passed(1).has_json_log(
        "test_creates_shipment.log",
        {"shipment_id": 77, "event": "отправление создано", "logger": "test-logger", "level": "info"},
    )


def test_keeps_structlog_events_of_other_tests_out(structlog_project: pytest.Pytester) -> None:
    structlog_project.makepyfile(
        """
        import structlog

        log = structlog.get_logger("test-logger")

        def test_opens_dispute():
            log.info("спор открыт")

        def test_closes_dispute():
            log.info("спор закрыт")
        """,
    )

    run = run_pytest(structlog_project)

    assert_run(run).passed(2).has_json_log_events("test_closes_dispute.log", "спор закрыт")


def test_keeps_bound_context_of_a_structlog_logger(structlog_project: pytest.Pytester) -> None:
    structlog_project.makepyfile(
        """
        import structlog

        def test_retries_request():
            log = structlog.get_logger("test-logger").bind(request_id="req-51")
            log.warning("странный ответ")
        """,
    )

    run = run_pytest(structlog_project)

    assert_run(run).passed(1).has_json_log_field(
        "test_retries_request.log",
        "request_id",
        "req-51",
    )


def test_renders_structlog_level_into_the_record(structlog_project: pytest.Pytester) -> None:
    structlog_project.makepyfile(
        """
        import structlog

        def test_reports_problem():
            structlog.get_logger("test-logger").warning("не хватает квоты")
        """,
    )

    run = run_pytest(structlog_project)

    assert_run(run).passed(1).has_json_log_field(
        "test_reports_problem.log",
        "level",
        "warning",
    )


def test_names_the_logger_of_a_stdlib_record(structlog_project: pytest.Pytester) -> None:
    structlog_project.makepyfile(
        """
        import logging

        def test_uses_stdlib_only():
            logging.getLogger("legacy.client").warning("таймаут")
        """,
    )

    run = run_pytest(structlog_project)

    assert_run(run).passed(1).has_json_log_field("test_uses_stdlib_only.log", "logger", "legacy.client")


def test_renders_stdlib_records_in_the_same_format(structlog_project: pytest.Pytester) -> None:
    structlog_project.makepyfile(
        """
        import logging

        import structlog

        def test_mixes_loggers():
            structlog.get_logger("test-logger").info("из structlog")
            logging.getLogger("legacy.client").warning("из stdlib")
        """,
    )

    run = run_pytest(structlog_project)

    assert_run(run).passed(1).has_json_log_events(
        "test_mixes_loggers.log",
        "из structlog",
        "из stdlib",
    )
