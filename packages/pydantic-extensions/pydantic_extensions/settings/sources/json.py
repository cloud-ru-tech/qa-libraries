from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from pydantic_settings.sources import JsonConfigSettingsSource

from .base_source_type import FileTypeBaseSettings, UnknownKeysFilteringMixin

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class JsonBaseSettings(FileTypeBaseSettings):
    """Base class for settings loaded from json files.

    Supply a file path or sequence of paths in the ``json_file`` property

    >>> class MySettings(JsonBaseSettings):
    >>>     ...  # settings
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
    """Strict JSON source with an explicit error for non-dictionaries.

    Raises:
        TypeError: If the JSON root is not a ``dict``.

    """

    def _read_file(self, file_path: Path | Traversable) -> dict[str, object]:
        data = cast("object", super()._read_file(file_path))
        if not isinstance(data, dict):
            message = f"Файл конфигурации не является dict: {file_path}"
            raise TypeError(message)
        return cast("dict[str, object]", data)

    def __call__(self) -> dict[str, object]:
        """Return settings values with the filter applied.

        :return: file source values.
        """
        return self.apply_unknown_keys_filter(cast("dict[str, object]", super().__call__()))
