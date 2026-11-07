"""Базовый класс настроек pydantic-settings с загрузкой значений из файла."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Protocol, cast

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources.utils import _get_alias_names


class FileSettingsConfigDict(SettingsConfigDict, total=False):
    """Настройки файловых источников с дополнительными проверками ключей."""

    validate_required_keys: bool
    validate_unknown_keys: bool


class UnknownKeysFilteringMixin:
    """Mixin для опциональной фильтрации неизвестных ключей из source-данных."""

    drop_unknown_keys: bool = False
    allowed_keys_filter: set[str] | None = None

    def set_unknown_keys_filter(self, allowed_keys: set[str]) -> None:
        """Ограничить источник известными ключами модели.

        :param allowed_keys: ключи, разрешённые для загрузки.
        """
        self.drop_unknown_keys = True
        self.allowed_keys_filter = allowed_keys

    def apply_unknown_keys_filter(self, data: dict[str, object]) -> dict[str, object]:
        """Удалить неизвестные ключи, если фильтр включён.

        :param data: значения файлового источника.
        :return: значения, допустимые для модели.
        """
        if self.drop_unknown_keys and self.allowed_keys_filter is not None:
            return {key: value for key, value in data.items() if key in self.allowed_keys_filter}
        return data


class SupportsUnknownKeysFiltering(Protocol):
    """Источник, умеющий отбрасывать неизвестные ключи."""

    def set_unknown_keys_filter(self, allowed_keys: set[str]) -> None:
        """Задать допустимые ключи.

        :param allowed_keys: ключи полей модели.
        """
        ...


class FileTypeBaseSettings(BaseSettings, ABC):
    """Базовый класс настроек из файла с кастомным приоритетом источников.

    Класс использует встроенные файловые источники `pydantic-settings`, но добавляет
    проектные правила валидации и собственный порядок источников:
    ``env -> dotenv -> secrets -> file -> init``.

    Путь к файлу берётся из ``settings_cls.model_config`` по ключу ``_paths_config_key``
    (например, ``json_file``).

    Основные особенности:
        1. Проверяет, что путь к конфигу задан в ``model_config``.
        2. Поддерживает один путь или список путей, разворачивает ``~``.
        3. Падает с ``FileNotFoundError``, если хотя бы один файл отсутствует.
        4. Проверяет файл на неизвестные ключи (лишние относительно модели).
        5. Проверяет файл на отсутствие обязательных ключей модели.
           Обе проверки можно отключить через ``model_config``.
        6. Учитывает алиасы полей и режимы ``populate_by_name`` / ``validate_by_name``.

    Attributes:
        _paths_config_key: Ключ в ``model_config`` с путём или списком путей к файлу.
        _encoding_config_key: Ключ в ``model_config`` с кодировкой или ``None``.
        _missing_paths_error: Текст ошибки, если путь к файлу не задан.

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
        """Создаёт файловый источник для конкретного формата.

        Args:
            settings_cls: Конкретный класс настроек, который сейчас инициализируется.
            raw_config: ``settings_cls.model_config`` в виде обычного словаря.

        Returns:
            Готовый экземпляр файлового источника.

        """
        ...

    @classmethod
    def _normalize_paths(cls, paths: object) -> list[Path]:
        """Нормализует путь(и) в список объектов ``Path`` с ``expanduser()``.

        Args:
            paths: Один путь или последовательность путей.

        Returns:
            Список нормализованных ``Path``.

        Raises:
            TypeError: Если передан не путь и не список путей.

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
        """Проверяет, что все пути к конфигам существуют.

        Args:
            paths: Нормализованный список путей к файлам конфигурации.
            paths_key: Ключ из ``model_config``, из которого взяты пути.

        Raises:
            FileNotFoundError: Если хотя бы один файл не найден.

        """
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            message = f"Файл(ы) конфигурации по ключу '{paths_key}' не найдены: {', '.join(missing)}"
            raise FileNotFoundError(message)

    @classmethod
    def _model_key_sets(cls, settings_cls: type[BaseSettings]) -> tuple[set[str], set[str]]:
        """Собирает множества допустимых и обязательных ключей модели.

        Args:
            settings_cls: Класс настроек с описанием полей модели.

        Returns:
            Кортеж ``(allowed_keys, required_keys)``:
            - ``allowed_keys``: алиасы и, при включении, имена полей;
            - ``required_keys``: ключи обязательных полей без ``default/default_factory``.

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
        """Проверяет, что обязательные ключи модели заданы в файле или другом источнике.

        Ключ считается отсутствующим только если его нет ни в файле, ни в одном из
        не-файловых источников (env / dotenv / secrets / init). Это позволяет задавать
        часть обязательных полей через переменные окружения, не дублируя их в файле.

        Args:
            source_data: Распарсенные данные файлового источника.
            required_keys: Множество обязательных ключей модели.
            provided_keys: Ключи, предоставленные не-файловыми источниками.

        Raises:
            ValueError: Если обязательные ключи отсутствуют во всех источниках.

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
        """Проверяет, что в файле нет неизвестных ключей.

        Args:
            source_data: Распарсенные данные файлового источника.
            allowed_keys: Множество допустимых ключей модели.

        Raises:
            ValueError: Если в файле присутствуют неизвестные ключи.

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
        """Собирает ключи верхнего уровня, заданные не-файловыми источниками.

        Нужно, чтобы обязательные поля, переданные через env / dotenv / secrets / init,
        не считались отсутствующими при проверке файлового конфига.

        Args:
            sources: Не-файловые источники настроек.

        Returns:
            Множество ключей, которые предоставляют переданные источники.

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
        """Проверяет целостность ключей в файле: обязательные и неизвестные.

        Args:
            settings_cls: Класс настроек, относительно которого валидируются ключи.
            file_source: Файловый источник, который возвращает распарсенные данные.
            validate_required_keys: Включена ли проверка обязательных ключей.
            validate_unknown_keys: Включена ли проверка неизвестных ключей.
            provided_keys: Ключи, предоставленные не-файловыми источниками.

        Raises:
            ValueError: Если отсутствуют обязательные ключи или есть неизвестные.

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
        """Собрать источники по приоритету и проверить файловый конфиг.

        :param settings_cls: конкретный класс настроек.
        :param init_settings: значения из конструктора модели.
        :param env_settings: значения переменных окружения.
        :param dotenv_settings: значения из dotenv-файлов.
        :param file_secret_settings: секреты из каталога.
        :return: источники в порядке env, dotenv, secrets, file, init.
        :raises ValueError: если путь не задан или ключи файла не соответствуют модели.
        :raises FileNotFoundError: если файл настроек отсутствует.
        :raises TypeError: если путь имеет неподдерживаемый тип.
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
