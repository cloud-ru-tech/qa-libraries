import os
from enum import Flag

from pydantic import AnyUrl, BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

env = os.environ.get("ENV", "dev")

DEFAULT_TIMEOUT_SECONDS = 10.0


class Destinations(Flag):
    """Notification destinations."""

    console = 0x1
    mattermost = 0x2
    telegram = 0x4


class MattermostSettings(BaseModel):
    """Mattermost webhook settings."""

    webhook_url: AnyUrl | None = None
    icon_emoji: str | None = None
    username: str | None = None
    channel: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    send_traceback: bool = True
    additional_message: str | None = None


class TelegramSettings(BaseModel):
    """Telegram notification settings."""

    bot_token: SecretStr | None = None
    chat_id: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    send_traceback: bool = True
    additional_message: str | None = None


class Settings(BaseSettings):
    """Notification channel settings from the environment."""

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
        """Read the channel bitmask.

        :param v: integer, numeric string, or an existing mask.
        :return: selected channels.
        :raises ValueError: if the value is not a bitmask.
        """
        if isinstance(v, Destinations):
            return v
        if isinstance(v, str):
            return Destinations(int(v))
        if isinstance(v, int):
            return Destinations(v)
        message = f"Cannot parse destinations from {v}"
        raise ValueError(message)
