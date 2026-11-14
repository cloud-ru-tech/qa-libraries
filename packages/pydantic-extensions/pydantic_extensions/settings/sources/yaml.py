from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from pydantic_settings.sources import YamlConfigSettingsSource

from .base_source_type import FileTypeBaseSettings, UnknownKeysFilteringMixin

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class YamlBaseSettings(FileTypeBaseSettings):
    """Base class for settings loaded from yaml files.

    Supply a file path or sequence of paths in the ``yaml_file`` property

    >>> class MySettings(YamlBaseSettings):
    >>>     ...  # settings
    >>>     model_config = SettingsConfigDict(yaml_file="config.yaml")
    """

    _paths_config_key: ClassVar[str] = "yaml_file"
    _encoding_config_key: ClassVar[str] = "yaml_file_encoding"
    _missing_paths_error: ClassVar[str] = "Не указан путь до yaml файла с настройками"

    @classmethod
    def _build_file_source(
        cls,
        settings_cls: type[BaseSettings],
        raw_config: dict[str, object],
    ) -> PydanticBaseSettingsSource:
        try:
            return StrictYamlConfigSettingsSource(
                settings_cls=settings_cls,
                yaml_file=cls._normalize_paths(raw_config.get(cls._paths_config_key)),
                yaml_file_encoding=cast("str | None", raw_config.get(cls._encoding_config_key)),
            )
        except ImportError as e:
            if "PyYAML is not installed" in str(e):
                message = (
                    "Для загрузки YAML настроек установите зависимость: "
                    'pip install "cloudru-qa-pydantic-extensions[yaml]"'
                )
                raise ImportError(message) from e
            raise


class StrictYamlConfigSettingsSource(UnknownKeysFilteringMixin, YamlConfigSettingsSource):
    """Strict YAML source with an explicit error for non-dictionaries.

    Raises:
        TypeError: If the YAML root is not a ``dict``.

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
