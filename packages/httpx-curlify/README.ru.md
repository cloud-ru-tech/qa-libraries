# httpx-curlify

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-httpx-curlify)](https://pypi.org/project/cloudru-qa-httpx-curlify/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-httpx-curlify)](https://pypi.org/project/cloudru-qa-httpx-curlify/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-httpx-curlify)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

[English](README.md) | Русский

Библиотека для преобразования HTTP-запросов из `httpx.Request` в формат curl-команд. Удобна для отладки, логирования и документирования API-запросов.

- [httpx-curlify](#httpx-curlify)
  - [Установка](#установка)
  - [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
  - [Использование](#использование)
    - [Базовое использование](#базовое-использование)
    - [Скрытие чувствительных данных](#скрытие-чувствительных-данных)
    - [Форматирование JSON](#форматирование-json)
  - [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-httpx-curlify
```

Библиотека импортируется как модуль `httpx_curlify`.

## Скиллы для AI-агентов

У этой библиотеки собственного скилла пока нет. Если в проекте установлены другие
библиотеки набора со [скиллами для AI-агентов](../../README.ru.md#скиллы-для-ai-агентов),
выбрать и подключить их можно из корня проекта (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

Для Claude Code добавьте `--claude`.

## Использование

### Базовое использование

Простое преобразование GET-запроса:

```python
import httpx
from httpx_curlify import to_curl

request = httpx.Request("GET", "https://example.com/api/users")
curl_command = to_curl(request)
print(curl_command)
```

Результат:
```bash
curl -X GET \
  -H 'host: example.com' \
  https://example.com/api/users
```

POST-запрос с JSON:

```python
request = httpx.Request(
    "POST",
    "https://example.com/api/users",
    json={"name": "John", "age": 30},
)
curl_command = to_curl(request)
print(curl_command)
```

Результат:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-length: 24' \
  -H 'content-type: application/json' \
  --json '{"name": "John", "age": 30}' \
  https://example.com/api/users
```

Запрос с заголовками:

```python
request = httpx.Request(
    "GET",
    "https://example.com/api/data",
    headers={
        "Authorization": "Bearer token123",
        "X-Custom-Header": "custom-value",
    },
)
curl_command = to_curl(request)
print(curl_command)
```

### Скрытие чувствительных данных

Библиотека поддерживает скрытие чувствительных данных в заголовках и JSON-теле запроса с использованием синтаксиса [glom](https://glom.readthedocs.io/en/latest/):

Скрытие заголовков:

```python
request = httpx.Request(
    "GET",
    "https://example.com/api/data",
    headers={
        "Authorization": "Bearer secret_token",
        "X-Api-Key": "api_key_value",
    },
)
curl_command = to_curl(request, sanitize_keys=["authorization", "x-api-key"])
print(curl_command)
```

Результат:
```bash
curl -X GET \
  -H 'host: example.com' \
  -H 'authorization: ****' \
  -H 'x-api-key: ****' \
  https://example.com/api/data
```

Скрытие данных в JSON:

```python
request = httpx.Request(
    "POST",
    "https://example.com/api/login",
    json={"username": "john", "password": "secret123"},
)
curl_command = to_curl(request, sanitize_keys=["password"])
print(curl_command)
```

Результат:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-type: application/json' \
  --json '{"username": "john", "password": "****"}' \
  https://example.com/api/login
```

Скрытие вложенных данных:

```python
request = httpx.Request(
    "POST",
    "https://example.com/api/data",
    json={"user": {"name": "John", "password": "secret"}},
)
curl_command = to_curl(request, sanitize_keys=["user.password"])
print(curl_command)
```

Результат:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-type: application/json' \
  --json '{"user": {"name": "John", "password": "****"}}' \
  https://example.com/api/data
```

### Форматирование JSON

Можно передать дополнительные параметры для `json.dumps`:

```python
request = httpx.Request(
    "POST",
    "https://example.com/api/data",
    json={"name": "John", "age": 30},
)
curl_command = to_curl(request, json_dumps_kwargs={"indent": 2})
print(curl_command)
```

Результат:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-type: application/json' \
  --json '{
    "name": "John",
    "age": 30
  }' \
  https://example.com/api/data
```

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                      # зависимости всех библиотек строго по uv.lock
make test-httpx-curlify        # тесты этой библиотеки
make typecheck-httpx-curlify   # mypy для этой библиотеки
make lint-fix                  # безопасные автоисправления ruff
make check                     # форматирование, ruff, mypy и тесты всего набора
```

Snapshot-тесты обновляются так:

```shell
make test-httpx-curlify PYTEST_ARGS=--snapshot-update
```

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-httpx-curlify PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `httpx-curlify/v<версия>`. Версия в теге должна совпадать с версией
в `packages/httpx-curlify/pyproject.toml`.
