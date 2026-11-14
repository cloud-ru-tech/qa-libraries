import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def isolate_nested_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load only plugins explicitly passed through ``-p`` in nested pytest runs.

    All plugins in the suite are installed in the shared workspace environment, and autoloading
    registers them again under different names.
    """
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


@pytest.fixture(autouse=True)
def isolate_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_NOTIFIER_DESTINATIONS", "1")
    monkeypatch.delenv("PYTEST_NOTIFIER_MATTERMOST__WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PYTEST_NOTIFIER_TELEGRAM__BOT_TOKEN", raising=False)
