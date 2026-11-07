import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def isolate_nested_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Загружать во вложенном pytest только плагины, явно переданные через ``-p``.

    В общем окружении workspace установлены все плагины набора, и автозагрузка
    регистрирует их повторно под другими именами.
    """
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


@pytest.fixture(autouse=True)
def isolate_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_NOTIFIER_DESTINATIONS", "1")
    monkeypatch.delenv("PYTEST_NOTIFIER_MATTERMOST__WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PYTEST_NOTIFIER_TELEGRAM__BOT_TOKEN", raising=False)
