from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from pydantic_settings.sources import JsonConfigSettingsSource

from .base_source_type import FileTypeBaseSettings, UnknownKeysFilteringMixin

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class JsonBaseSettings(FileTypeBaseSettings):
    """Базовый класс для настроек, загружаемых из json файлов.

    Необходимо передать путь до файла или последовательность путей в свойство ``json_file``

    >>> class MySettings(JsonBaseSettings):
    >>>     ...  # настройки
    >>>     model_config = SettingsConfigDict(json_file="config.json")
    """

    _paths_config_key: ClassVar[str] = "json_file"
    _encoding_config_key: ClassVar[str] = "json_file_encoding"
    _missing_paths_error: ClassVar[str] = "Не указан путь до json файла с настройками"

    @classmethod
    def _build_file_source(
        cls,
        settings_cls: type[BaseSettings],
        raw_config: dict[str, object],
    ) -> PydanticBaseSettingsSource:
        return StrictJsonConfigSettingsSource(
            settings_cls=settings_cls,
            json_file=cls._normalize_paths(raw_config.get(cls._paths_config_key)),
            json_file_encoding=cast("str | None", raw_config.get(cls._encoding_config_key)),
        )


class StrictJsonConfigSettingsSource(UnknownKeysFilteringMixin, JsonConfigSettingsSource):
    """Строгий JSON-источник с явной ошибкой для не-словаря.

    Raises:
        TypeError: Если корень JSON не является ``dict``.

    """

    def _read_file(self, file_path: Path | Traversable) -> dict[str, object]:
        data = cast("object", super()._read_file(file_path))
        if not isinstance(data, dict):
            message = f"Файл конфигурации не является dict: {file_path}"
            raise TypeError(message)
        return cast("dict[str, object]", data)

    def __call__(self) -> dict[str, object]:
        """Вернуть значения настроек с применённым фильтром.

        :return: значения файлового источника.
        """
        return self.apply_unknown_keys_filter(cast("dict[str, object]", super().__call__()))
