from abc import ABC, abstractmethod

from pytest_notifier.models import TestResults
from pytest_notifier.settings import Settings


class NotifierBase(ABC):
    """Base class for all notifiers."""

    def __init__(self, settings: Settings) -> None:
        """Save notification settings.

        :param settings: channel settings.
        """
        self.settings = settings

    @abstractmethod
    def send(self, results: TestResults) -> None:
        """Send a notification about test results."""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check whether the notifier is enabled and configured correctly."""
