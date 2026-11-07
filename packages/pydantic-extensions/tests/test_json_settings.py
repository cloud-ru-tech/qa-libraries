from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from assertpy import assert_that
from pydantic import BaseModel, Field, ValidationError
from pydantic_extensions.settings import FileSettingsConfigDict as SettingsConfigDict
from pydantic_extensions.settings import JsonBaseSettings

if TYPE_CHECKING:
    from pathlib import Path


def test_json_settings(tmp_path: Path) -> None:
    """Тест загрузки настроек из json файла."""
    json_content: str = """
    {
        "name": "test_app",
        "debug": true,
        "port": 8000
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)

        model_config = SettingsConfigDict(json_file=str(config_file))

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)


def test_json_settings_submodels(tmp_path: Path) -> None:
    """Тест загрузки настроек из json файла с вложенными моделями."""
    json_content: str = """
    {
        "name": "test_app",
        "debug": true,
        "port": 8000,
        "submodel": {
            "name": "submodel_name",
            "value": 100
        }
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(JsonBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(json_file=str(config_file))

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_json_settings_multiple_files(tmp_path: Path) -> None:
    """Тест загрузки настроек из нескольких json файлов."""
    json_content_main: str = """
    {
        "name": "test_app",
        "debug": true,
        "port": 8000
    }
    """
    json_content_submodel: str = """
    {
        "submodel": {
            "name": "submodel_name",
            "value": 100
        }
    }
    """
    config_file_main = tmp_path / f"config_main_{uuid4()}.json"
    config_file_submodel = tmp_path / f"config_submodel_{uuid4()}.json"
    config_file_main.write_text(json_content_main)
    config_file_submodel.write_text(json_content_submodel)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(JsonBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(json_file=[config_file_main, config_file_submodel])

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_json_settings_with_env(tmp_path: Path) -> None:
    """Тест загрузки настроек из json файла с переопределением через переменные окружения."""
    json_content: str = """
    {
        "name": "test_app",
        "debug": true,
        "port": 8000
    }
    """
    env_content: str = """
    NAME=test_app_overriden
    SUBMODEL__NAME=submodel_name
    SUBMODEL__VALUE=100
    """
    config_file_json = tmp_path / f"config_main_{uuid4()}.json"
    config_file_env = tmp_path / f"config_submodel_{uuid4()}.env"

    config_file_json.write_text(json_content)
    config_file_env.write_text(env_content)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(JsonBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(
            env_nested_delimiter="__",
            env_file=config_file_env,
            json_file=config_file_json,
        )

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app_overriden")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_json_settings_raises_error_when_file_not_specified() -> None:
    """Тест проверяет, что при отсутствии объявления json_file возникает ошибка."""

    class TestSettings(JsonBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict()

    with pytest.raises(ValueError, match="Не указан путь до json файла с настройками"):
        TestSettings()


def test_json_settings_raises_error_when_file_not_found() -> None:
    """Тест проверяет, что при отсутствии файла возникает ошибка."""

    class TestSettings(JsonBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict(json_file="non_existent_file.json")

    with pytest.raises(FileNotFoundError):
        TestSettings()


def test_json_settings_raises_error_when_json_is_list(tmp_path: Path) -> None:
    """Тест проверяет, что когда json содержит список, то возникает ошибка."""
    json_content: str = """
    [
        "item1",
        "item2",
        "item3"
    ]
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        items: list[str] = Field(default=[])

        model_config = SettingsConfigDict(json_file=str(config_file))

    with pytest.raises(TypeError, match="Файл конфигурации не является dict"):
        TestSettings()


def test_json_settings_validation_error_on_invalid_type(tmp_path: Path) -> None:
    """Тест проверяет валидацию типов данных."""
    json_content: str = """
    {
        "port": "not_a_number"
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        port: int = Field(default=0)
        model_config = SettingsConfigDict(json_file=str(config_file))

    with pytest.raises(ValidationError):
        TestSettings()


def test_json_settings_uses_custom_encoding(tmp_path: Path) -> None:
    """Тест проверяет работу с пользовательской кодировкой файла."""
    json_content: str = """
    {
        "message": "привет мир"
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file_encoding = "windows-1251"
    config_file.write_text(json_content, encoding=config_file_encoding)

    class TestSettings(JsonBaseSettings):
        message: str = Field(default="")
        model_config = SettingsConfigDict(
            json_file=config_file,
            json_file_encoding=config_file_encoding,
        )

    settings = TestSettings()

    assert_that(settings.message).is_equal_to("привет мир")


def test_json_settings_raises_error_on_unknown_keys(tmp_path: Path) -> None:
    """Тест проверяет, что лишние ключи в json вызывают ошибку."""
    json_content: str = """
    {
        "name": "test_app",
        "unknown_key": "value"
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        name: str = Field(default="")
        model_config = SettingsConfigDict(json_file=str(config_file))

    with pytest.raises(ValueError, match="неизвестные ключи: unknown_key"):
        TestSettings()


def test_json_settings_raises_error_on_missing_required_keys(tmp_path: Path) -> None:
    """Тест проверяет, что отсутствие обязательного ключа в json вызывает ошибку."""
    json_content: str = """
    {
        "debug": true
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        app_name: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(json_file=str(config_file))

    with pytest.raises(ValueError, match="отсутствуют ключи: app_name"):
        TestSettings()


def test_json_settings_raises_error_on_multiple_missing_required_keys(tmp_path: Path) -> None:
    """Тест проверяет, что перечисляются все отсутствующие обязательные ключи."""
    json_content: str = """
    {
        "debug": true
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        app_name: str
        host: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(json_file=str(config_file))

    with pytest.raises(ValueError, match="отсутствуют ключи: app_name, host"):
        TestSettings()


def test_json_settings_skips_unknown_keys_validation_when_disabled(tmp_path: Path) -> None:
    """Тест проверяет отключение валидации неизвестных ключей."""
    json_content: str = """
    {
        "name": "test_app",
        "unknown_key": "value"
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        name: str = Field(default="")
        model_config = SettingsConfigDict(
            json_file=str(config_file),
            validate_unknown_keys=False,
        )

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")


def test_json_settings_skips_required_keys_validation_when_disabled(tmp_path: Path) -> None:
    """Тест проверяет отключение валидации обязательных ключей."""
    json_content: str = """
    {
        "debug": true
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(
            json_file=str(config_file),
            validate_required_keys=False,
        )

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("")
    assert_that(settings.debug).is_true()


def test_json_settings_raises_validation_error_for_required_without_default_when_check_disabled(
    tmp_path: Path,
) -> None:
    """Тест проверяет, что pydantic валидирует required поле без default."""
    json_content: str = """
    {
        "debug": true
    }
    """
    config_file = tmp_path / f"config_{uuid4()}.json"
    config_file.write_text(json_content)

    class TestSettings(JsonBaseSettings):
        app_name: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(
            json_file=str(config_file),
            validate_required_keys=False,
        )

    with pytest.raises(ValidationError):
        TestSettings()


def test_rejects_non_path_item_in_config_sequence(tmp_path: Path) -> None:
    class Settings(JsonBaseSettings):
        model_config = SettingsConfigDict(json_file=cast("list[str]", [str(tmp_path / "settings.json"), 17]))

    with pytest.raises(TypeError, match="путь"):
        Settings()
