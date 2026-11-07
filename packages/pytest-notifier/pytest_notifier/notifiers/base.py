from abc import ABC, abstractmethod

from pytest_notifier.models import TestResults
from pytest_notifier.settings import Settings


class NotifierBase(ABC):
    """Базовый класс для всех нотификаторов."""

    def __init__(self, settings: Settings) -> None:
        """Сохранить настройки уведомлений.

        :param settings: настройки каналов.
        """
        self.settings = settings

    @abstractmethod
    def send(self, results: TestResults) -> None:
        """Отправить уведомление о результатах тестов."""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Проверить, включён ли нотификатор и настроен ли корректно."""
