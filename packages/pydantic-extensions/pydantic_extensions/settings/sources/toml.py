from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from pydantic_settings.sources import TomlConfigSettingsSource

from .base_source_type import FileTypeBaseSettings, UnknownKeysFilteringMixin

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class TomlBaseSettings(FileTypeBaseSettings):
    """Базовый класс для настроек, загружаемых из toml файлов.

    Необходимо передать путь до файла или последовательность путей в свойство ``toml_file``

    >>> class MySettings(TomlBaseSettings):
    >>>     ...  # настройки
    >>>     model_config = SettingsConfigDict(toml_file="config.toml")
    """

    _paths_config_key: ClassVar[str] = "toml_file"
    _encoding_config_key: ClassVar[str | None] = None
    _missing_paths_error: ClassVar[str] = "Не указан путь до toml файла с настройками"

    @classmethod
    def _build_file_source(
        cls,
        settings_cls: type[BaseSettings],
        raw_config: dict[str, object],
    ) -> PydanticBaseSettingsSource:
        return StrictTomlConfigSettingsSource(
            settings_cls=settings_cls,
            toml_file=cls._normalize_paths(raw_config.get(cls._paths_config_key)),
        )


class StrictTomlConfigSettingsSource(UnknownKeysFilteringMixin, TomlConfigSettingsSource):
    """TOML-источник с поддержкой фильтрации неизвестных ключей."""

    def __call__(self) -> dict[str, object]:
        """Вернуть значения настроек с применённым фильтром.

        :return: значения файлового источника.
        """
        return self.apply_unknown_keys_filter(cast("dict[str, object]", super().__call__()))
