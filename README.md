# [Cloud.ru](https://cloud.ru) QA libraries

[![Security](https://github.com/cloud-ru-tech/qa-libraries/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/cloud-ru-tech/qa-libraries/actions/workflows/security.yml)
[![Python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/cloud-ru-tech/qa-libraries)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

Python-библиотеки для автотестов. Каждая библиотека — отдельный пакет в PyPI
со своей версией и релизами.

## Идея

Вместо одного большого клиента, который умеет всё сразу, — маленький базовый клиент и рядом
набор небольших библиотек, которые подключаются к нему опциями. Базовый HTTP-клиент только
отправляет запросы, а повторы, авторизация, структурированные логи и шаги Allure — отдельные
пакеты. Каждый собирает из них свой SDK: ставит то, что нужно, и не тянет зависимости того,
чем не пользуется.

Опции покрывают то, что тестировщикам нужно чаще всего, поэтому писать свои обёртки
не приходится: установил пакет, импортировал опцию, подключил к клиенту — в любом проекте.

```python
import structlog
from http_client import HttpClient, options
from http_client_allure import wrap_requests_in_steps
from http_client_auth import IAM_Auth, IAM_HttpClient
from http_client_retries import with_retries_failed_requests
from http_client_structlog import with_structlogger

auth = IAM_Auth("key_id", "key_secret", IAM_HttpClient("https://iam.example.com"))
client = HttpClient(
    "https://api.example.com",
    options.with_auth(auth),
    with_retries_failed_requests(),
    with_structlogger(structlog.get_logger()),
    wrap_requests_in_steps(),
)
```

Опция — обычная функция, которая получает клиент в конструкторе и настраивает его. Поэтому
своё расширение пишется так же, как библиотечное, и подключается наравне с ними:

```python
from http_client import BaseHttpClient, ClientOption, HttpClient
from http_client_retries import with_retries_failed_requests
from httpx import Request


def with_region(region: str) -> ClientOption:
    def add_region(request: Request) -> None:
        request.headers["X-Region"] = region

    def option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_region)

    return option


client = HttpClient("https://api.example.com", with_region("ru-central-1"), with_retries_failed_requests())
```

По той же схеме устроены gRPC, SSH и MCP-клиенты: они тоже принимают опции `ClientOption`.

## Библиотеки

**HTTP**

- [`http-client`](packages/http-client) — базовый HTTP-клиент на httpx
- [`http-client-auth`](packages/http-client-auth) — авторизация токенами IAM
- [`http-client-retries`](packages/http-client-retries) — повторные попытки запросов
- [`http-client-responses`](packages/http-client-responses) — типизированные ответы с моделями pydantic
- [`http-client-structlog`](packages/http-client-structlog) — структурированные логи через structlog
- [`http-client-allure`](packages/http-client-allure) — запросы и ответы в отчёте Allure
- [`httpx-curlify`](packages/httpx-curlify) — запрос httpx в виде команды curl

**gRPC**

- [`grpc-client`](packages/grpc-client) — базовый gRPC-клиент на grpcio
- [`grpc-client-auth`](packages/grpc-client-auth) — авторизация токенами IAM
- [`grpc-client-structlog`](packages/grpc-client-structlog) — структурированные логи через structlog

**Другие клиенты**

- [`ssh-client`](packages/ssh-client) — SSH-клиент
- [`mcp-client`](packages/mcp-client) — клиент для серверов MCP

**Инструменты для тестов**

- [`explicit-wait`](packages/explicit-wait) — явные ожидания событий
- [`logging-context`](packages/logging-context) — отдельный файл логов на каждый тест
- [`pytest-notifier`](packages/pytest-notifier) — уведомления об упавших тестах
- [`pydantic-extensions`](packages/pydantic-extensions) — расширения pydantic: поля и настройки из файлов

## Установка

Нужен Python 3.13 или новее. Библиотеки ставятся по отдельности:

```shell
pip install cloudru-qa-http-client
```

Модуль импортируется без префикса: `cloudru-qa-http-client` → `import http_client`.
Опции, примеры и дополнительные зависимости описаны в README каждой библиотеки.

## Скиллы для AI-агентов

Вместе с библиотеками поставляются скиллы — инструкции и примеры, которые помогают AI-агенту правильно использовать их API.

Установите нужные библиотеки в окружение своего проекта, затем из его корня выполните:

```shell
uvx library-skills
```

Команда найдёт скиллы установленных библиотек и предложит выбрать нужные. Они подключаются
в `.agents/skills` проекта. Для Claude Code используйте `uvx library-skills --claude`:
скиллы также будут доступны в `.claude/skills`.

По умолчанию создаются символические ссылки: при обновлении библиотеки обновляются
и инструкции для агента. Список возможностей установщика — в [документации Library Skills](https://library-skills.io/use/).
Исходники наших скиллов находятся в [`.agents/skills`](.agents/skills).

## Разработка

Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make и [`checkmake`](https://github.com/checkmake/checkmake), для тестов gRPC и SSH-клиентов — Docker. Все команды запускаются из корня репозитория:

```shell
make sync              # зависимости всех библиотек строго по uv.lock
make check             # форматирование, линтеры, mypy и тесты всего набора
make test-http-client  # тесты одной библиотеки
make help              # все доступные цели
```

Тесты прогоняются на Python 3.13 и 3.14: `make sync test PYTHON_VERSION=3.14`.

Изменения принимаются через pull request в `master`. Правила — в [CONTRIBUTING.md](CONTRIBUTING.md).

## Релизы

Каждая библиотека выпускается git-тегом `<имя>/v<версия>`, например `http-client/v1.0.0`.
Версия в теге должна совпадать с версией в `packages/<имя>/pyproject.toml`. После проверок
CI публикует пакет в PyPI.

## Лицензия

[Apache-2.0](LICENSE)
