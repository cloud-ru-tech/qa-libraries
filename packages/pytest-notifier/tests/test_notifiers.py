import httpx
import pytest
from assertpy import assert_that
from pydantic import AnyUrl, SecretStr
from pytest_notifier.models import TestFailureInfo as FailureInfo
from pytest_notifier.models import TestResults as Results
from pytest_notifier.notifiers.mattermost import MattermostNotifier
from pytest_notifier.notifiers.telegram import TelegramNotifier
from pytest_notifier.plugin import get_active_notifiers
from pytest_notifier.settings import Destinations, MattermostSettings, Settings, TelegramSettings


@pytest.fixture()
def requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    captured: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200)

    client_class = httpx.Client

    def client(*, timeout: float) -> httpx.Client:
        return client_class(timeout=timeout, transport=httpx.MockTransport(capture))

    monkeypatch.setattr(httpx, "Client", client)
    return captured


@pytest.fixture()
def failure_results() -> Results:
    failure = FailureInfo("test.py::test_cart", "test_cart", "test.py", "stock exhausted", "trace details", 0.25)
    return Results(1, 0, 1, 0, 0, 0, 0, 1, "TESTS_FAILED", failures=[failure])


def test_console_is_default_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_NOTIFIER_DESTINATIONS")

    assert_that(Settings().destinations).is_equal_to(Destinations.console)


def test_numeric_environment_selects_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_NOTIFIER_DESTINATIONS", "5")

    assert_that(Settings().destinations).is_equal_to(Destinations.console | Destinations.telegram)


def test_skips_remote_channels_without_credentials() -> None:
    settings = Settings(destinations=Destinations.mattermost | Destinations.telegram)

    assert_that(get_active_notifiers(settings)).is_empty()


def test_mattermost_posts_failure_details(requests: list[httpx.Request], failure_results: Results) -> None:
    settings = Settings(mattermost=MattermostSettings(webhook_url=AnyUrl("https://notifications.example/hook")))

    MattermostNotifier(settings).send(failure_results)

    assert_that(requests[0].content.decode()).contains("test_cart", "stock exhausted", "trace details")


def test_mattermost_omits_disabled_traceback(requests: list[httpx.Request], failure_results: Results) -> None:
    settings = Settings(
        mattermost=MattermostSettings(webhook_url=AnyUrl("https://hooks.example/results"), send_traceback=False)
    )

    MattermostNotifier(settings).send(failure_results)

    assert_that(requests[0].content.decode()).does_not_contain("trace details")


def test_telegram_posts_to_configured_chat(requests: list[httpx.Request], failure_results: Results) -> None:
    settings = Settings(telegram=TelegramSettings(bot_token=SecretStr("fake-token"), chat_id="case-chat"))

    TelegramNotifier(settings).send(failure_results)

    assert_that(requests[0].content.decode()).contains("case-chat", "stock exhausted", "trace details")


def test_telegram_omits_disabled_traceback(requests: list[httpx.Request], failure_results: Results) -> None:
    settings = Settings(
        telegram=TelegramSettings(bot_token=SecretStr("fake-other"), chat_id="other-chat", send_traceback=False)
    )

    TelegramNotifier(settings).send(failure_results)

    assert_that(requests[0].content.decode()).does_not_contain("trace details")
