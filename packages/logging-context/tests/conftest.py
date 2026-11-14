import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def isolate_nested_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only plugins explicitly passed through ``-p`` in nested pytest runs.

    All plugins in the suite are installed in the shared workspace environment, and autoloading
    registers them again under different names.
    """
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


@pytest.fixture()
def logging_project(pytester: pytest.Pytester) -> pytest.Pytester:
    """Project with the plugin enabled and a logger configured at import time."""
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
