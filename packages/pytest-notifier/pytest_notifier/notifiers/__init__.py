from pytest_notifier.settings import Destinations

from .base import NotifierBase
from .console import ConsoleNotifier
from .mattermost import MattermostNotifier
from .telegram import TelegramNotifier

__all__ = [
    "NOTIFIER_REGISTRY",
    "ConsoleNotifier",
    "MattermostNotifier",
    "NotifierBase",
    "TelegramNotifier",
]

NOTIFIER_REGISTRY: dict[Destinations, type[NotifierBase]] = {
    Destinations.console: ConsoleNotifier,
    Destinations.mattermost: MattermostNotifier,
    Destinations.telegram: TelegramNotifier,
}
