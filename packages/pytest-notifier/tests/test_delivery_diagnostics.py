import logging
from collections.abc import Callable
from typing import cast

import httpx2
import pytest
from assertpy import assert_that
from pydantic import AnyUrl, SecretStr
from pytest_notifier.models import TestFailureInfo as FailureInfo
from pytest_notifier.models import TestResults as Results
from pytest_notifier.notifiers import MattermostNotifier, NotifierBase, TelegramNotifier
from pytest_notifier.settings import MattermostSettings, Settings, TelegramSettings

BOT_CREDENTIAL = "synthetic-bot-token"
WEBHOOK = "https://chat.example/hooks/synthetic-webhook?key=synthetic-query"
SECRETS = (BOT_CREDENTIAL, "synthetic-webhook", "synthetic-query")


@pytest.fixture(params=["Telegram", "Mattermost"])
def channel(request: pytest.FixtureRequest) -> tuple[str, NotifierBase]:
    notifiers = {
        "Telegram": TelegramNotifier(
            Settings(telegram=TelegramSettings(bot_token=SecretStr(BOT_CREDENTIAL), chat_id="test"))
        ),
        "Mattermost": MattermostNotifier(Settings(mattermost=MattermostSettings(webhook_url=AnyUrl(WEBHOOK)))),
    }
    name = cast("str", request.param)
    return name, notifiers[name]


@pytest.fixture()
def results() -> Results:
    failure = FailureInfo("test.py::test_cart", "test_cart", "test.py", "empty cart", None, 0.1)
    return Results(1, 0, 1, 0, 0, 0, 0, 1, "TESTS_FAILED", failures=[failure])


@pytest.fixture()
def use_transport(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable[[httpx2.Request], httpx2.Response]], None]:
    client_class = httpx2.Client

    def install(handler: Callable[[httpx2.Request], httpx2.Response]) -> None:
        def client(*, timeout: float) -> httpx2.Client:
            return client_class(timeout=timeout, transport=httpx2.MockTransport(handler))

        monkeypatch.setattr(httpx2, "Client", client)

    return install


def test_credentials_reach_the_configured_endpoint(
    channel: tuple[str, NotifierBase],
    results: Results,
    use_transport: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
) -> None:
    name, notifier = channel
    expected = {"Telegram": f"https://api.telegram.org/bot{BOT_CREDENTIAL}/sendMessage", "Mattermost": WEBHOOK}
    targets: list[str] = []

    def deliver(request: httpx2.Request) -> httpx2.Response:
        targets.append(str(request.url))
        return httpx2.Response(202)

    use_transport(deliver)
    notifier.send(results)

    assert_that(targets).is_equal_to([expected[name]])


def test_success_logs_only_channel_and_status(
    channel: tuple[str, NotifierBase],
    results: Results,
    use_transport: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    name, notifier = channel
    unrelated_url = "https://service.example/health"
    core_logger = logging.getLogger("httpcore2.http11.trace")

    def healthy(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200)

    with httpx2.Client(transport=httpx2.MockTransport(healthy)) as unrelated:

        def deliver(request: httpx2.Request) -> httpx2.Response:
            core_logger.debug("Location: %s", request.url)
            core_logger.debug("unrelated connection opened")
            unrelated.get(unrelated_url)
            return httpx2.Response(202)

        use_transport(deliver)
        with caplog.at_level(logging.DEBUG):
            notifier.send(results)

    assert_that(caplog.text).contains(
        f"{name}: HTTP 202", unrelated_url, "unrelated connection opened"
    ).does_not_contain(*SECRETS)


def test_status_error_omits_credentials_from_logs_and_exception(
    channel: tuple[str, NotifierBase],
    results: Results,
    use_transport: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    name, notifier = channel
    use_transport(lambda _: httpx2.Response(403))

    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match=f"{name}: HTTP 403") as error:
        notifier.send(results)

    assert_that(caplog.text + str(error.value)).contains(f"{name}: HTTP 403").does_not_contain(*SECRETS)


def test_transport_error_omits_url_from_diagnostics(
    channel: tuple[str, NotifierBase],
    results: Results,
    use_transport: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    name, notifier = channel

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(str(request.url), request=request)

    use_transport(refuse)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match=f"{name}: ConnectError") as error:
        notifier.send(results)

    assert_that(caplog.text + str(error.value)).contains(f"{name}: ConnectError").does_not_contain(*SECRETS)
