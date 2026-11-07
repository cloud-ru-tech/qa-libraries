from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from pydantic_settings.sources import YamlConfigSettingsSource

from .base_source_type import FileTypeBaseSettings, UnknownKeysFilteringMixin

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class YamlBaseSettings(FileTypeBaseSettings):
    """Базовый класс для настроек, загружаемых из yaml файлов.

    Необходимо передать путь до файла или последовательность путей в свойство ``yaml_file``

    >>> class MySettings(YamlBaseSettings):
    >>>     ...  # настройки
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
    """Строгий YAML-источник с явной ошибкой для не-словаря.

    Raises:
        TypeError: Если корень YAML не является ``dict``.

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
