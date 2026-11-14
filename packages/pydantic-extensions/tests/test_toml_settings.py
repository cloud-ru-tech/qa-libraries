from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from assertpy import assert_that
from pydantic import BaseModel, Field, ValidationError
from pydantic_extensions.settings import FileSettingsConfigDict as SettingsConfigDict
from pydantic_extensions.settings import TomlBaseSettings

if TYPE_CHECKING:
    from pathlib import Path


def test_toml_settings(tmp_path: Path) -> None:
    """Test loading settings from a toml file."""
    toml_content: str = """
    name = "test_app"
    debug = true
    port = 8000
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)

        model_config = SettingsConfigDict(toml_file=str(config_file))

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)


def test_toml_settings_submodels(tmp_path: Path) -> None:
    """Test loading settings from a toml file with nested models."""
    toml_content: str = """
    name = "test_app"
    debug = true
    port = 8000
    [submodel]
    name = "submodel_name"
    value = 100
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(TomlBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(toml_file=str(config_file))

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_toml_settings_multiple_files(tmp_path: Path) -> None:
    """Test loading settings from multiple toml files."""
    toml_content_main: str = """
    name = "test_app"
    debug = true
    port = 8000
    """
    toml_content_submodel: str = """
    [submodel]
    name = "submodel_name"
    value = 100
    """
    config_file_main = tmp_path / f"config_main_{uuid4()}.toml"
    config_file_submodel = tmp_path / f"config_submodel_{uuid4()}.toml"
    config_file_main.write_text(toml_content_main)
    config_file_submodel.write_text(toml_content_submodel)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(TomlBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(toml_file=[config_file_main, config_file_submodel])

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_toml_settings_raises_error_when_file_not_specified() -> None:
    """Test that a missing toml_file declaration raises an error."""

    class TestSettings(TomlBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict()

    with pytest.raises(ValueError, match="Не указан путь до toml файла с настройками"):
        TestSettings()


def test_toml_settings_raises_error_when_file_not_found() -> None:
    """Test that a missing file raises an error."""

    class TestSettings(TomlBaseSettings):
        app_name: str = Field(default="")
        model_config = SettingsConfigDict(toml_file="non_existent_file.toml")

    with pytest.raises(FileNotFoundError):
        TestSettings()


def test_toml_settings_validation_error_on_invalid_type(tmp_path: Path) -> None:
    """Test data type validation."""
    toml_content: str = """
    port = "not_a_number"
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        port: int = Field(default=0)
        model_config = SettingsConfigDict(toml_file=str(config_file))

    with pytest.raises(ValidationError):
        TestSettings()


def test_toml_settings_with_env(tmp_path: Path) -> None:
    """Test loading settings from a toml file with environment variable overrides."""
    toml_content: str = """
    name = "test_app"
    debug = true
    port = 8000
    """
    env_content: str = """
    NAME=test_app_overriden
    SUBMODEL__NAME=submodel_name
    SUBMODEL__VALUE=100
    """
    config_file_toml = tmp_path / f"config_main_{uuid4()}.toml"
    config_file_env = tmp_path / f"config_submodel_{uuid4()}.env"

    config_file_toml.write_text(toml_content)
    config_file_env.write_text(env_content)

    class SubModel(BaseModel):
        name: str = Field(default="")
        value: int = Field(default=0)

    class TestSettings(TomlBaseSettings):
        name: str = Field(default="")
        debug: bool = Field(default=False)
        port: int = Field(default=0)
        submodel: SubModel = Field(default_factory=SubModel)

        model_config = SettingsConfigDict(
            env_nested_delimiter="__",
            env_file=config_file_env,
            toml_file=config_file_toml,
        )

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app_overriden")
    assert_that(settings.debug).is_true()
    assert_that(settings.port).is_equal_to(8000)
    assert_that(settings.submodel.name).is_equal_to("submodel_name")
    assert_that(settings.submodel.value).is_equal_to(100)


def test_toml_settings_raises_error_on_unknown_keys(tmp_path: Path) -> None:
    """Test that extra toml keys raise an error."""
    toml_content: str = """
    name = "test_app"
    unknown_key = "value"
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        name: str = Field(default="")
        model_config = SettingsConfigDict(toml_file=str(config_file))

    with pytest.raises(ValueError, match="неизвестные ключи: unknown_key"):
        TestSettings()


def test_toml_settings_raises_error_on_missing_required_keys(tmp_path: Path) -> None:
    """Test that a missing required toml key raises an error."""
    toml_content: str = """
    debug = true
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        app_name: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(toml_file=str(config_file))

    with pytest.raises(ValueError, match="отсутствуют ключи: app_name"):
        TestSettings()


def test_toml_settings_raises_error_on_multiple_missing_required_keys(tmp_path: Path) -> None:
    """Test that all missing required keys are listed."""
    toml_content: str = """
    debug = true
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        app_name: str
        host: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(toml_file=str(config_file))

    with pytest.raises(ValueError, match="отсутствуют ключи: app_name, host"):
        TestSettings()


def test_toml_settings_skips_unknown_keys_validation_when_disabled(tmp_path: Path) -> None:
    """Test disabling unknown key validation."""
    toml_content: str = """
    name = "test_app"
    unknown_key = "value"
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        name: str = Field(default="")
        model_config = SettingsConfigDict(
            toml_file=str(config_file),
            validate_unknown_keys=False,
        )

    settings = TestSettings()

    assert_that(settings.name).is_equal_to("test_app")


def test_toml_settings_skips_required_keys_validation_when_disabled(tmp_path: Path) -> None:
    """Test disabling required key validation."""
    toml_content: str = """
    debug = true
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        app_name: str = Field(default="")
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(
            toml_file=str(config_file),
            validate_required_keys=False,
        )

    settings = TestSettings()

    assert_that(settings.app_name).is_equal_to("")
    assert_that(settings.debug).is_true()


def test_toml_settings_raises_validation_error_for_required_without_default_when_check_disabled(
    tmp_path: Path,
) -> None:
    """Test that pydantic validates a required field without a default."""
    toml_content: str = """
    debug = true
    """
    config_file = tmp_path / f"config_{uuid4()}.toml"
    config_file.write_text(toml_content)

    class TestSettings(TomlBaseSettings):
        app_name: str
        debug: bool = Field(default=False)
        model_config = SettingsConfigDict(
            toml_file=str(config_file),
            validate_required_keys=False,
        )

    with pytest.raises(ValidationError):
        TestSettings()
