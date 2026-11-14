import httpx

from pytest_notifier.models import TestResults
from pytest_notifier.settings import Settings

from .base import NotifierBase


class TelegramNotifier(NotifierBase):
    """Notifier that sends results to Telegram through the Bot API."""

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self, settings: Settings) -> None:
        """Save notification settings.

        :param settings: channel settings.
        """
        super().__init__(settings)
        self.tg = settings.telegram

    def is_enabled(self) -> bool:
        """Check the configured channel availability.

        :return: whether the settings are sufficient for sending.
        """
        return self.tg.bot_token is not None and self.tg.chat_id is not None

    def send(self, results: TestResults) -> None:
        """Send messages about failed tests.

        :param results: run results.
        """
        all_failures = results.failures + results.errors
        for _, failure in enumerate(all_failures, 1):
            lines = [
                f"Test failed: *{failure.name}*",
                "",
                f"nodeid: `{failure.nodeid}`",
                f"duration: {failure.duration:.2f}s",
                "failure:",
                f"```\n{failure.error_message}\n```",
            ]

            if failure.traceback and self.settings.telegram.send_traceback:
                lines.extend(
                    [
                        "",
                        "traceback:",
                        f"```\n{failure.traceback}\n```",
                    ]
                )

            if self.tg.additional_message:
                lines.extend(
                    [
                        "",
                        self.tg.additional_message,
                    ]
                )

            message = "\n".join(lines)
            self._send_message(message)

    def _send_message(self, text: str) -> None:
        if self.tg.bot_token is None:
            return
        bot_token = self.tg.bot_token.get_secret_value()
        url = f"{self.BASE_URL}{bot_token}/sendMessage"

        payload = {
            "chat_id": self.tg.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        with httpx.Client(timeout=self.tg.timeout_seconds) as client:
            client.post(url, json=payload).raise_for_status()
