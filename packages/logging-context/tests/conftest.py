import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def isolate_nested_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Загружать во вложенном pytest только плагины, явно переданные через ``-p``.

    В общем окружении workspace установлены все плагины набора, и автозагрузка
    регистрирует их повторно под другими именами.
    """
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


@pytest.fixture()
def logging_project(pytester: pytest.Pytester) -> pytest.Pytester:
    """Проект с активированным плагином и логгером, настроенным при импорте."""
    pytester.makeini(
        """
        [pytest]
        logging_context_dir = logs
        logging_context_loggers = test-logger
        logging_context_format = %(levelname)s - %(message)s
        logging_context_attach_allure = false
        logging_context_log_test_header = false
        """,
    )
    pytester.makeconftest(
        """
        import logging

        logger = logging.getLogger("test-logger")
        """,
    )
    return pytester
