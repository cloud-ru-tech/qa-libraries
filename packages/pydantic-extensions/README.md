# Pydantic extensions

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-pydantic-extensions)](https://pypi.org/project/cloudru-qa-pydantic-extensions/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-pydantic-extensions)](https://pypi.org/project/cloudru-qa-pydantic-extensions/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-pydantic-extensions)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Extensions for [`pydantic`](https://docs.pydantic.dev/latest/).

- [Pydantic extensions](#pydantic-extensions)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Usage](#usage)
    - [The `fields` module](#the-fields-module)
      - [Serialization and deserialization](#serialization-and-deserialization)
    - [The `settings` module](#the-settings-module)
      - [File key validation](#file-key-validation)
      - [YAML settings](#yaml-settings)
      - [JSON settings](#json-settings)
      - [TOML settings](#toml-settings)
      - [Encoding support](#encoding-support)
      - [Loading multiple files](#loading-multiple-files)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-pydantic-extensions
```

Import the library as the module `pydantic_extensions`.

## Skills for AI agents

This library does not have its own skill yet. If your project uses other
libraries from this suite with [skills for AI agents](https://github.com/cloud-ru-tech/qa-libraries#skills-for-ai-agents),
select and enable them from your project root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

For Claude Code, add `--claude`.

## Usage

### The `fields` module

This module extends fields in pydantic models.

#### Serialization and deserialization

`CamelCaseBaseModel` and `PascalCaseBaseModel` convert field names to [`camelCase`](https://en.wikipedia.org/wiki/Camel_case) and `PascalCase`, respectively, when converting pydantic models to and from JSON.


```python
from pydantic_extensions.fields import CamelCaseBaseModel


class User(CamelCaseBaseModel):
    username: str
    last_name: str
    is_active: bool


# Serialization
user = User(username="John", last_name="Smith", is_active=True)
assert user.model_dump_json() == '{"username":"John","lastName":"Smith","isActive":true}'

# Deserialization
json_content = {"username": "Aleksey", "lastName": "Petrov", "isActive": false}
user2 = User.model_validate(json_content)
assert user2.last_name == "Petrov"
```

### The `settings` module

This module extends [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

#### Features

`JsonBaseSettings`, `TomlBaseSettings`, and `YamlBaseSettings` share these rules:

- Custom source order: `env -> dotenv -> secrets -> file -> init`.
- Support for a single file or a list of files.
- All specified files must exist (`FileNotFoundError`).
- Unknown file keys are rejected (`ValueError`).
- All required model keys must be present in the file or another source (env / dotenv / secrets / init) (`ValueError`).
- JSON/YAML files must have a `dict` root (`TypeError`).

#### File key validation

`JsonBaseSettings`, `TomlBaseSettings`, and `YamlBaseSettings` support two `SettingsConfigDict` flags:

- `validate_unknown_keys` (default `True`): reject unknown file keys.
- `validate_required_keys` (default `True`): check required model keys when reading the source. A key is missing only if it is absent from both the file and all other sources (env / dotenv / secrets / init). Required fields can therefore be set through environment variables without duplicating them in the file.

Strict mode (default):

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import JsonBaseSettings


class MySettings(JsonBaseSettings):
    app_name: str
    debug: bool = Field(default=False)

    model_config = SettingsConfigDict(
        json_file="config.json",
        validate_unknown_keys=True,
        validate_required_keys=True,
    )
```

Ignore unknown keys:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import TomlBaseSettings


class MySettings(TomlBaseSettings):
    app_name: str = Field(default="")

    model_config = SettingsConfigDict(
        toml_file="config.toml",
        validate_unknown_keys=False,
    )
```

With `validate_unknown_keys=False`, extra keys are filtered out of the file source automatically, so `extra="ignore"` is not needed.

Disable early validation of required keys:

```python
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str
    debug: bool = False

    model_config = SettingsConfigDict(
        yaml_file="config.yaml",
        validate_required_keys=False,
    )
```

In this mode, the library does not check required keys when reading the file. Final pydantic model validation still runs.

If a field has a default value, a missing file key does not cause an error; the `default` is used:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str = Field(default="my-app")
    debug: bool = Field(default=False)

    model_config = SettingsConfigDict(
        yaml_file="config.yaml",
        validate_required_keys=False,
    )


settings = MySettings()
# If config.yaml has no app_name, settings.app_name == "my-app"
```

If no `default` is set, pydantic raises `ValidationError`:

```python
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str

    model_config = SettingsConfigDict(
        yaml_file="config.yaml",
        validate_required_keys=False,
    )


MySettings()  # ValidationError if app_name is missing from config.yaml
```

#### YAML settings

Use `YamlBaseSettings` to load settings from one or more YAML files:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str = Field(default="")
    debug: bool = Field(default=False)
    port: int = Field(default=0)

    model_config = SettingsConfigDict(yaml_file="config.yaml")
```

Install the extra dependency for YAML support:
```shell
pip install "cloudru-qa-pydantic-extensions[yaml]"
```

#### JSON settings

Use `JsonBaseSettings` to load settings from one or more JSON files:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import JsonBaseSettings


class MySettings(JsonBaseSettings):
    app_name: str = Field(default="")
    debug: bool = Field(default=False)
    port: int = Field(default=0)

    model_config = SettingsConfigDict(json_file="config.json")
```

#### TOML settings

Use `TomlBaseSettings` to load settings from one or more TOML files:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import TomlBaseSettings


class MySettings(TomlBaseSettings):
    app_name: str = Field(default="")
    debug: bool = Field(default=False)
    port: int = Field(default=0)

    model_config = SettingsConfigDict(toml_file="config.toml")
```

Install the extra dependency for TOML support:
```shell
pip install "cloudru-qa-pydantic-extensions[toml]"
``` 

#### Encoding support

For YAML and JSON settings, set the file encoding with `*_file_encoding`:

```python
model_config = SettingsConfigDict(yaml_file="config.yaml", yaml_file_encoding="windows-1251")
```

#### Loading multiple files

All settings classes support loading multiple files. This is useful when each environment has its own file alongside a shared settings file. For example, with YAML:

```python
import os

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings

ENV = os.getenv("ENV")


class MySettings(YamlBaseSettings):
    app_name: str = Field(default="")
    debug: bool = Field(default=False)
    port: int = Field(default=0)

    model_config = SettingsConfigDict(
        yaml_file=[
            "config.common.yaml",
            f"config.{ENV}.yaml",
        ],
    )
```

If a variable occurs in both files, its value comes from the last file, `config.{ENV}.yaml` in this example.

YAML, TOML, and JSON configuration files can also be combined with `.env` files:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str = Field(default="")
    debug: bool = Field(default=False)
    port: int = Field(default=0)

    # Read configuration from both env and YAML files.
    # Source priority: env -> dotenv -> secrets -> file -> init.
    model_config = SettingsConfigDict(
        env_file=".env",
        yaml_file=f"config.yaml",
    )
```

## Development

This library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make
and [`checkmake`](https://github.com/checkmake/checkmake);
run the commands from the repository root:

```shell
make sync                            # dependencies and extras for all libraries from uv.lock
make test-pydantic-extensions        # tests for this library
make typecheck-pydantic-extensions   # mypy for this library
make check                           # formatting, Ruff, mypy, and tests for the whole suite
```

⚠️ Keep the library lightweight and general purpose. Add dependencies only
when they are needed by all library users.
Make heavy dependencies optional (see
[the uv documentation](https://docs.astral.sh/uv/concepts/projects/dependencies/#optional-dependencies)).

Tests run on Python 3.13 and 3.14. Each version uses a separate environment:
`make sync test-pydantic-extensions PYTHON_VERSION=3.14`.

Create a release with the Git tag `pydantic-extensions/v<version>`. The tag version must match
the version in `packages/pydantic-extensions/pyproject.toml`.
