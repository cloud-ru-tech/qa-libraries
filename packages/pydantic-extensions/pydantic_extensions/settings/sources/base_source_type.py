"""Base pydantic-settings class that loads values from a file."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Protocol, cast

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources.utils import _get_alias_names


class FileSettingsConfigDict(SettingsConfigDict, total=False):
    """File source settings with additional key validation."""

    validate_required_keys: bool
    validate_unknown_keys: bool


class UnknownKeysFilteringMixin:
    """Mixin for optional filtering of unknown keys from source data."""

    drop_unknown_keys: bool = False
    allowed_keys_filter: set[str] | None = None

    def set_unknown_keys_filter(self, allowed_keys: set[str]) -> None:
        """Limit the source to known model keys.

        :param allowed_keys: keys allowed for loading.
        """
        self.drop_unknown_keys = True
        self.allowed_keys_filter = allowed_keys

    def apply_unknown_keys_filter(self, data: dict[str, object]) -> dict[str, object]:
        """Remove unknown keys if filtering is enabled.

        :param data: file source values.
        :return: values allowed by the model.
        """
        if self.drop_unknown_keys and self.allowed_keys_filter is not None:
            return {key: value for key, value in data.items() if key in self.allowed_keys_filter}
        return data


class SupportsUnknownKeysFiltering(Protocol):
    """Source capable of dropping unknown keys."""

    def set_unknown_keys_filter(self, allowed_keys: set[str]) -> None:
        """Set the allowed keys.

        :param allowed_keys: model field keys.
        """
        ...


class FileTypeBaseSettings(BaseSettings, ABC):
    """Base file settings class with custom source priority.

    The class uses built-in `pydantic-settings` file sources but adds
    project-specific validation rules and a custom source order:
    ``env -> dotenv -> secrets -> file -> init``.

    Read the file path from ``settings_cls.model_config`` using ``_paths_config_key``
    (for example, ``json_file``).

    Key features:
        1. Check that the configuration path is set in ``model_config``.
        2. Support one path or a list of paths and expand ``~``.
        3. Raise ``FileNotFoundError`` if any file is missing.
        4. Check the file for unknown keys (extra keys relative to the model).
        5. Check the file for missing required model keys.
           Both checks can be disabled through ``model_config``.
        6. Respect field aliases and ``populate_by_name`` / ``validate_by_name`` modes.

    Attributes:
        _paths_config_key: ``model_config`` key containing a file path or list of paths.
        _encoding_config_key: ``model_config`` key containing the encoding, or ``None``.
        _missing_paths_error: Error text if no file path is set.

    """

    _paths_config_key: ClassVar[str]
    _encoding_config_key: ClassVar[str | None]
    _missing_paths_error: ClassVar[str]
    _validate_required_keys_config_key: ClassVar[str] = "validate_required_keys"
    _validate_unknown_keys_config_key: ClassVar[str] = "validate_unknown_keys"

    @classmethod
    @abstractmethod
    def _build_file_source(
        cls,
        settings_cls: type[BaseSettings],
        raw_config: dict[str, object],
    ) -> PydanticBaseSettingsSource:
        """Create a file source for a specific format.

        Args:
            settings_cls: Concrete settings class currently being initialized.
            raw_config: ``settings_cls.model_config`` as a regular dictionary.

        Returns:
            Ready-to-use file source instance.

        """
        ...

    @classmethod
    def _normalize_paths(cls, paths: object) -> list[Path]:
        """Normalize paths into a list of ``Path`` objects using ``expanduser()``.

        Args:
            paths: Single path or sequence of paths.

        Returns:
            List of normalized ``Path`` objects.

        Raises:
            TypeError: If neither a path nor a list of paths is supplied.

        """
        if isinstance(paths, (str, Path)):
            path_items: Sequence[str | Path] = [paths]
        elif isinstance(paths, Sequence):
            path_items = []
            for path in cast("Sequence[object]", paths):
                if not isinstance(path, (str, Path)):
                    message = f"Ожидается путь, получено: {type(path).__name__}"
                    raise TypeError(message)
                path_items.append(path)
        else:
            message = f"Ожидается путь или список путей, получено: {type(paths).__name__}"
            raise TypeError(message)

        return [Path(path).expanduser() for path in path_items]

    @classmethod
    def _validate_paths_exist(cls, paths: list[Path], paths_key: str) -> None:
        """Check that all configuration paths exist.

        Args:
            paths: Normalized list of configuration file paths.
            paths_key: ``model_config`` key from which paths were obtained.

        Raises:
            FileNotFoundError: If any file is missing.

        """
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            message = f"Файл(ы) конфигурации по ключу '{paths_key}' не найдены: {', '.join(missing)}"
            raise FileNotFoundError(message)

    @classmethod
    def _model_key_sets(cls, settings_cls: type[BaseSettings]) -> tuple[set[str], set[str]]:
        """Collect sets of allowed and required model keys.

        Args:
            settings_cls: Settings class defining the model fields.

        Returns:
            A tuple of ``(allowed_keys, required_keys)``:
            - ``allowed_keys``: aliases and, when enabled, field names;
            - ``required_keys``: required field keys without ``default/default_factory``.

        """
        allowed: set[str] = set()
        required: set[str] = set()
        include_name = bool(
            settings_cls.model_config.get("populate_by_name", False)
            or settings_cls.model_config.get("validate_by_name", False)
        )
        for field_name, field in settings_cls.model_fields.items():
            aliases = cast("tuple[list[str], object]", _get_alias_names(field_name, field))[0]
            allowed.update(aliases)
            if include_name:
                allowed.add(field_name)
            if not field.is_required():
                continue
            required.add(aliases[0] if aliases else field_name)
        return allowed, required

    @classmethod
    def _ensure_no_missing_keys(
        cls,
        source_data: dict[str, object],
        required_keys: set[str],
        provided_keys: set[str],
    ) -> None:
        """Check that required model keys are set in the file or another source.

        A key is missing only if absent from both the file and all
        non-file sources (env / dotenv / secrets / init). This allows setting
        some required fields through environment variables without duplicating them in the file.

        Args:
            source_data: Parsed file source data.
            required_keys: Set of required model keys.
            provided_keys: Keys provided by non-file sources.

        Raises:
            ValueError: If required keys are missing from every source.

        """
        missing_keys = sorted(required_keys - set(source_data) - provided_keys)
        if missing_keys:
            message = f"В файле конфигурации отсутствуют ключи: {', '.join(missing_keys)}"
            raise ValueError(message)

    @classmethod
    def _ensure_no_unknown_keys(
        cls,
        source_data: dict[str, object],
        allowed_keys: set[str],
    ) -> None:
        """Check that the file contains no unknown keys.

        Args:
            source_data: Parsed file source data.
            allowed_keys: Set of allowed model keys.

        Raises:
            ValueError: If the file contains unknown keys.

        """
        unknown_keys = sorted(set(source_data) - allowed_keys)
        if unknown_keys:
            message = f"В файле конфигурации найдены неизвестные ключи: {', '.join(unknown_keys)}"
            raise ValueError(message)

    @classmethod
    def _collect_provided_keys(
        cls,
        sources: Sequence[PydanticBaseSettingsSource],
    ) -> set[str]:
        """Collect top-level keys provided by non-file sources.

        Ensure required fields supplied through env / dotenv / secrets / init
        are not considered missing when validating the file configuration.

        Args:
            sources: Non-file settings sources.

        Returns:
            Set of keys provided by the supplied sources.

        """
        provided: set[str] = set()
        for source in sources:
            provided.update(cast("dict[str, object]", source()))
        return provided

    @classmethod
    def _validate_file_keys_consistency(
        cls,
        settings_cls: type[BaseSettings],
        file_source: PydanticBaseSettingsSource,
        *,
        validate_required_keys: bool,
        validate_unknown_keys: bool,
        provided_keys: set[str],
    ) -> None:
        """Validate required and unknown keys in the file.

        Args:
            settings_cls: Settings class used to validate keys.
            file_source: File source that returns parsed data.
            validate_required_keys: Whether required key validation is enabled.
            validate_unknown_keys: Whether unknown key validation is enabled.
            provided_keys: Keys provided by non-file sources.

        Raises:
            ValueError: If required keys are missing or unknown keys are present.

        """
        source_data = cast("dict[str, object]", file_source())
        allowed_keys, required_keys = cls._model_key_sets(settings_cls)
        if validate_required_keys:
            cls._ensure_no_missing_keys(source_data, required_keys, provided_keys)
        if validate_unknown_keys:
            cls._ensure_no_unknown_keys(source_data, allowed_keys)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Arrange sources by priority and validate the file configuration.

        :param settings_cls: concrete settings class.
        :param init_settings: values from the model constructor.
        :param env_settings: environment variable values.
        :param dotenv_settings: values from dotenv files.
        :param file_secret_settings: secrets from a directory.
        :return: sources in env, dotenv, secrets, file, init order.
        :raises ValueError: if no path is set or file keys do not match the model.
        :raises FileNotFoundError: if the settings file is missing.
        :raises TypeError: if a path has an unsupported type.
        """
        paths_key = cls._paths_config_key

        raw_config = cast("dict[str, object]", settings_cls.model_config)
        if not raw_config.get(paths_key):
            missing_msg = cls._missing_paths_error
            raise ValueError(missing_msg)

        paths = cls._normalize_paths(raw_config[paths_key])
        cls._validate_paths_exist(paths, paths_key)

        validate_required_keys = bool(raw_config.get(cls._validate_required_keys_config_key, True))
        validate_unknown_keys = bool(raw_config.get(cls._validate_unknown_keys_config_key, True))
        file_source = cls._build_file_source(settings_cls, raw_config)
        if not validate_unknown_keys:
            allowed_keys, _ = cls._model_key_sets(settings_cls)
            filterable_source = cast("SupportsUnknownKeysFiltering", file_source)
            filterable_source.set_unknown_keys_filter(allowed_keys)
        provided_keys = cls._collect_provided_keys(
            (env_settings, dotenv_settings, file_secret_settings, init_settings),
        )
        cls._validate_file_keys_consistency(
            settings_cls,
            file_source,
            validate_required_keys=validate_required_keys,
            validate_unknown_keys=validate_unknown_keys,
            provided_keys=provided_keys,
        )
        return (
            env_settings,
            dotenv_settings,
            file_secret_settings,
            file_source,
            init_settings,
        )
