import os
from enum import Flag

from pydantic import AnyUrl, BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

env = os.environ.get("ENV", "dev")

DEFAULT_TIMEOUT_SECONDS = 10.0


class Destinations(Flag):
    """Пункты назначения отправки нотфикаций."""

    console = 0x1
    mattermost = 0x2
    telegram = 0x4


class MattermostSettings(BaseModel):
    """Настройки webhook Mattermost."""

    webhook_url: AnyUrl | None = None
    icon_emoji: str | None = None
    username: str | None = None
    channel: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    send_traceback: bool = True
    additional_message: str | None = None


class TelegramSettings(BaseModel):
    """Настройки уведомлений Telegram."""

    bot_token: SecretStr | None = None
    chat_id: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    send_traceback: bool = True
    additional_message: str | None = None


class Settings(BaseSettings):
    """Настройки каналов уведомления из окружения."""

    destinations: Destinations = Destinations.console
    mattermost: MattermostSettings = MattermostSettings()
    telegram: TelegramSettings = TelegramSettings()

    model_config = SettingsConfigDict(
        extra="ignore",
        env_prefix="PYTEST_NOTIFIER_",
        env_nested_delimiter="__",
        env_file=[".env", f".{env}.env"],
    )

    @field_validator("destinations", mode="before")
    @classmethod
    def parse_destinations(cls, v: object) -> Destinations:
        """Прочитать битовую маску каналов.

        :param v: целое число, строка с числом или готовая маска.
        :return: выбранные каналы.
        :raises ValueError: если значение не является битовой маской.
        """
        if isinstance(v, Destinations):
            return v
        if isinstance(v, str):
            return Destinations(int(v))
        if isinstance(v, int):
            return Destinations(v)
        message = f"Cannot parse destinations from {v}"
        raise ValueError(message)
