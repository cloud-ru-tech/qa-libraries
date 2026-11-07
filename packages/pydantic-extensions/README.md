# Расширения Pydantic

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-pydantic-extensions)](https://pypi.org/project/cloudru-qa-pydantic-extensions/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-pydantic-extensions)](https://pypi.org/project/cloudru-qa-pydantic-extensions/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-pydantic-extensions)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Расширения для библиотеки [`pydantic`](https://docs.pydantic.dev/latest/).

- [Расширения Pydantic](#расширения-pydantic)
  - [Установка](#установка)
  - [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
  - [Использование](#использование)
    - [Модуль `fields`](#модуль-fields)
      - [Сериализация и десериализация](#сериализация-и-десериализация)
    - [Модуль `settings`](#модуль-settings)
      - [Управление проверкой ключей в файле](#управление-проверкой-ключей-в-файле)
      - [YAML настройки](#yaml-настройки)
      - [JSON настройки](#json-настройки)
      - [TOML настройки](#toml-настройки)
      - [Поддержка кодировки](#поддержка-кодировки)
      - [Загрузка из нескольких файлов](#загрузка-из-нескольких-файлов)
  - [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-pydantic-extensions
```

Библиотека импортируется как модуль `pydantic_extensions`.

## Скиллы для AI-агентов

У этой библиотеки собственного скилла пока нет. Если в проекте установлены другие
библиотеки набора со [скиллами для AI-агентов](https://github.com/cloud-ru-tech/qa-libraries#скиллы-для-ai-агентов),
выбрать и подключить их можно из корня проекта (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

Для Claude Code добавьте `--claude`.

## Использование

### Модуль `fields`

Данный модуль содержит расширения для полей pydantic моделей.

#### Сериализация и десериализация

Классы `CamelCaseBaseModel` и `PascalCaseBaseModel` позволяют при конвертации pydantic модели в json и обратно модифицировать названия в формате [`cammelCase`](https://ru.wikipedia.org/wiki/%D0%92%D0%B5%D1%80%D0%B1%D0%BB%D1%8E%D0%B6%D0%B8%D0%B9_%D1%80%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80) и `PascalCase` соответственно.


```python
from pydantic_extensions.fields import CamelCaseBaseModel


class User(CamelCaseBaseModel):
    username: str
    last_name: str
    is_active: bool


# Сериализация
user = User(username="John", last_name="Smith", is_active=True)
assert user.model_dump_json() == '{"username":"John","lastName":"Smith","isActive":true}'

# Десериализация
json_content = {"username": "Aleksey", "lastName": "Petrov", "isActive": false}
user2 = User.model_validate(json_content)
assert user2.last_name == "Petrov"
```

### Модуль `settings`

Данный модуль содержит расширения для настроек [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). 

#### Особенности

Для `JsonBaseSettings`, `TomlBaseSettings` и `YamlBaseSettings` действуют общие правила:

- Кастомный порядок источников: `env -> dotenv -> secrets -> file -> init`.
- Поддержка одного файла или списка файлов.
- Проверка, что все указанные файлы существуют (`FileNotFoundError`).
- Проверка отсутствия неизвестных ключей в файле (`ValueError`).
- Проверка наличия всех обязательных ключей модели — в файле либо в другом источнике (env / dotenv / secrets / init) (`ValueError`).
- Для JSON/YAML: корень файла должен быть `dict` (`TypeError`).

#### Управление проверкой ключей в файле

Для `JsonBaseSettings`, `TomlBaseSettings` и `YamlBaseSettings` доступны 2 флага в `SettingsConfigDict`:

- `validate_unknown_keys` (по умолчанию `True`) - проверять отсутствие лишних ключей в файле.
- `validate_required_keys` (по умолчанию `True`) - проверять наличие обязательных ключей модели на этапе чтения source. Ключ считается отсутствующим, только если его нет ни в файле, ни в одном из не-файловых источников (env / dotenv / secrets / init) — поэтому часть обязательных полей можно задавать через переменные окружения, не дублируя их в файле.

Строгий режим (по умолчанию):

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

Игнорировать неизвестные ключи:

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

При `validate_unknown_keys=False` лишние ключи автоматически отфильтровываются из файлового source, поэтому дополнительно задавать `extra="ignore"` не требуется.

Отключить раннюю проверку обязательных ключей:

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

В этом режиме библиотека не проверяет обязательные ключи на этапе чтения файла, но итоговая pydantic-валидация модели по-прежнему выполняется.

Если у поля задано значение по умолчанию, то отсутствие ключа в файле не приведет к ошибке, и будет использован `default`:

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
# если в config.yaml нет app_name, то settings.app_name == "my-app"
```

Если `default` не задан, pydantic выбросит `ValidationError`:

```python
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str

    model_config = SettingsConfigDict(
        yaml_file="config.yaml",
        validate_required_keys=False,
    )


MySettings()  # ValidationError, если app_name отсутствует в config.yaml
```

#### YAML настройки

Для загрузки настроек из YAML файла(ов) реализован класс `YamlBaseSettings`:

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

Для работы с YAML файлами требуется установить дополнительную зависимость:
```shell
pip install "cloudru-qa-pydantic-extensions[yaml]"
```

#### JSON настройки

Для загрузки настроек из JSON файла(ов) реализован класс `JsonBaseSettings`:

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

#### TOML настройки

Для загрузки настроек из TOML файла(ов) реализован класс `TomlBaseSettings`:

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

Для работы с TOML файлами требуется установить дополнительную зависимость:
```shell
pip install "cloudru-qa-pydantic-extensions[toml]"
``` 

#### Поддержка кодировки

Для yaml и json настроек есть поддержка кодировки файла через параметр `*_file_encoding`:

```python
model_config = SettingsConfigDict(yaml_file="config.yaml", yaml_file_encoding="windows-1251")
```

#### Загрузка из нескольких файлов

Для всех классов реализована поддержка загрузки настроек сразу из нескольких файлов. Это бывает полезно, когда у вас есть несколько файлов для каждого окружения и один файл с общими для всех окружений настройками. На примере YAML настроек:

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

Если какая-либо переменная будет продублирована в обоих файлах, то ее значение будет взято из последнего файла. В данном случае из `config.{ENV}.yaml`.

Также yaml, toml и json файлы с конфигурацией можно сочетать с `.env` файлами:

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from pydantic_extensions.settings import YamlBaseSettings


class MySettings(YamlBaseSettings):
    app_name: str = Field(default="")
    debug: bool = Field(default=False)
    port: int = Field(default=0)

    # Конфигурация считывается одновременно из env и yaml файлов.
    # Приоритет источников: env -> dotenv -> secrets -> file -> init.
    model_config = SettingsConfigDict(
        env_file=".env",
        yaml_file=f"config.yaml",
    )
```

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                            # зависимости и extras всех библиотек строго по uv.lock
make test-pydantic-extensions        # тесты этой библиотеки
make typecheck-pydantic-extensions   # mypy для этой библиотеки
make check                           # форматирование, ruff, mypy и тесты всего набора
```

⚠️ **Важно**, чтобы библиотека оставалась легковесной и универсальной. Новые зависимости стоит
добавлять, только если есть уверенность, что они необходимы всем пользователям библиотеки.
Тяжёлые зависимости лучше оформлять как optional (подробнее
[в документации uv](https://docs.astral.sh/uv/concepts/projects/dependencies/#optional-dependencies)).

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-pydantic-extensions PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `pydantic-extensions/v<версия>`. Версия в теге должна совпадать
с версией в `packages/pydantic-extensions/pyproject.toml`.
