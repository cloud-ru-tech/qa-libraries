from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from assertpy import assert_that
from pydantic import BaseModel, Field, ValidationError
from pydantic_extensions.settings import FileSettingsConfigDict as SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings

if TYPE_CHECKING:
    from pathlib import Path


def test_yaml_settings(tmp_path: Path) -> None:
    """Test loading settings from a yaml file."""
    yaml_content: str = """
    app_name: test_app
    debug: true
    port: 8000
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)

        model_config = SettingsConfigDict(yaml_file=str(config_file))

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)


def test_yaml_settings_submodels(tmp_path: Path) -> None:
    """Test loading settings from a yaml file with nested models."""
    yaml_content: str = """
    app_name: test_app
    debug: true
    port: 8000
    submodel:
      name: submodel_name
      value: 100
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(yaml_file=str(config_file))

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_yaml_settings_multiple_files(tmp_path: Path) -> None:
    """Test loading settings from multiple yaml files."""
    yaml_content_main: str = """
    app_name: test_app
    debug: true
    port: 8000
    """
    yaml_content_submodel: str = """
    submodel:
      name: submodel_name
      value: 100
    """
    config_file_main = tmp_path / f"config_main_{uuid4()}.yaml"
    config_file_submodel = tmp_path / f"config_submodel_{uuid4()}.yaml"

    config_file_main.write_text(yaml_content_main)
    config_file_submodel.write_text(yaml_content_submodel)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(yaml_file=[config_file_main, config_file_submodel])

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_yaml_settings_with_env(tmp_path: Path) -> None:
    """Test loading settings from multiple yaml files."""
    yaml_content: str = """
    app_name: test_app
    debug: true
    port: 8000
    """
    env_content: str = """
    APP_NAME=test_app_overriden
    SUBMODEL__NAME=submodel_name
    SUBMODEL__VALUE=100
    """
    config_file_yaml = tmp_path / f"config_main_{uuid4()}.yaml"
    config_file_env = tmp_path / f"config_submodel_{uuid4()}.env"

    config_file_yaml.write_text(yaml_content)
    config_file_env.write_text(env_content)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(
            env_nested_delimiter="__",
            env_file=config_file_env,
            yaml_file=config_file_yaml,
        )

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("test_app_overriden")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_yaml_settings_required_key_from_env_not_in_file(tmp_path: Path) -> None:
    """A required field without a default may come from env rather than a file."""
    yaml_content: str = """
    app_name: test_app
    """
    env_content: str = "API_KEY=secret-from-env"
    config_file_yaml = tmp_path / f"config_{uuid4()}.yaml"
    config_file_env = tmp_path / f"config_{uuid4()}.env"

    config_file_yaml.write_text(yaml_content)
    config_file_env.write_text(env_content)

    class TestSettings(YamlBaseSettings):
        app_name: str
        api_key: str

        model_config = SettingsConfigDict(
            env_file=config_file_env,
            yaml_file=config_file_yaml,
        )

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("test_app")
    assert_that(settings.api_key).is_equal_to("secret-from-env")


def test_yaml_settings_raises_when_required_key_absent_in_all_sources(tmp_path: Path) -> None:
    """Validation fails if a required key is missing from both the file and env."""
    yaml_content: str = """
    app_name: test_app
    """
    env_content: str = "OTHER=value"
    config_file_yaml = tmp_path / f"config_{uuid4()}.yaml"
    config_file_env = tmp_path / f"config_{uuid4()}.env"

    config_file_yaml.write_text(yaml_content)
    config_file_env.write_text(env_content)

    class TestSettings(YamlBaseSettings):
        app_name: str
        api_key: str

        model_config = SettingsConfigDict(
            env_file=config_file_env,
            yaml_file=config_file_yaml,
        )

    with pytest.raises(ValueError, match="отсутствуют ключи: api_key"):
        TestSettings()


def test_yaml_settings_uses_custom_encoding(tmp_path: Path) -> None:
    """Test using a custom file encoding."""
    yaml_content: str = """
    message: привет мир
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file_encoding = "windows-1251"
    config_file.write_text(yaml_content, encoding=config_file_encoding)

    class TestSettings(YamlBaseSettings):
        message: str = Field(default="")
        model_config = SettingsConfigDict(
            yaml_file=config_file,
            yaml_file_encoding=config_file_encoding,
        )

    settings = TestSettings()

    assert_that(settings.message).is_equal_to("привет мир")


def test_yaml_settings_raises_error_when_file_not_specified() -> None:
    """Test that a missing yaml_file declaration raises an error."""

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict()

    with pytest.raises(ValueError, match="Не указан путь до yaml файла с настройками"):
        TestSettings()


def test_yaml_settings_raises_error_when_file_not_found() -> None:
    """Test that a missing file raises an error."""

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict(yaml_file="non_existent_file.yaml")

    with pytest.raises(FileNotFoundError):
        TestSettings()


def test_yaml_settings_raises_error_when_yaml_is_list(tmp_path: Path) -> None:
    """Test that a yaml list raises an error."""
    yaml_content: str = """
    - item1
    - item2
    - item3
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        items: list[str] = Field(default=[])

        model_config = SettingsConfigDict(yaml_file=str(config_file))

    with pytest.raises(TypeError, match="Файл конфигурации не является dict"):
        TestSettings()


def test_yaml_settings_validation_error_on_invalid_type(tmp_path: Path) -> None:
    """Test data type validation."""
    yaml_content: str = """
    port: not_a_number
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        port: int = Field(default=0)
        model_config = SettingsConfigDict(yaml_file=str(config_file))

    with pytest.raises(ValidationError):
        TestSettings()


def test_yaml_settings_raises_error_on_unknown_keys(tmp_path: Path) -> None:
    """Test that extra yaml keys raise an error."""
    yaml_content: str = """
    app_name: test_app
    unknown_key: value
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict(yaml_file=str(config_file))

    with pytest.raises(ValueError, match="неизвестные ключи: unknown_key"):
        TestSettings()


def test_yaml_settings_raises_error_on_missing_required_keys(tmp_path: Path) -> None:
    """Test that a missing required yaml key raises an error."""
    yaml_content: str = """
    debug: true
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(yaml_file=str(config_file))

    with pytest.raises(ValueError, match="отсутствуют ключи: app_name"):
        TestSettings()


def test_yaml_settings_raises_error_on_multiple_missing_required_keys(tmp_path: Path) -> None:
    """Test that all missing required keys are listed."""
    yaml_content: str = """
    debug: true
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str
        host: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(yaml_file=str(config_file))

    with pytest.raises(ValueError, match="отсутствуют ключи: app_name, host"):
        TestSettings()


def test_yaml_settings_skips_unknown_keys_validation_when_disabled(tmp_path: Path) -> None:
    """Test disabling unknown key validation."""
    yaml_content: str = """
    app_name: test_app
    unknown_key: value
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict(
            yaml_file=str(config_file),
            validate_unknown_keys=False,
        )

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("test_app")


def test_yaml_settings_skips_required_keys_validation_when_disabled(tmp_path: Path) -> None:
    """Test disabling required key validation."""
    yaml_content: str = """
    debug: true
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(
            yaml_file=str(config_file),
            validate_required_keys=False,
        )

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("")
    assert_that(settings.debug).is_true()


def test_yaml_settings_raises_validation_error_for_required_without_default_when_check_disabled(
    tmp_path: Path,
) -> None:
    """Test that pydantic validates a required field without a default."""
    yaml_content: str = """
    debug: true
    """
    config_file = tmp_path / f"config_{uuid4()}.yaml"
    config_file.write_text(yaml_content)

    class TestSettings(YamlBaseSettings):
        app_name: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(
            yaml_file=str(config_file),
            validate_required_keys=False,
        )

    with pytest.raises(ValidationError):
        TestSettings()
