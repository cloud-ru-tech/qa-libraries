# Авторизация для HTTP-клиента

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-auth)](https://pypi.org/project/cloudru-qa-http-client-auth/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-auth)](https://pypi.org/project/cloudru-qa-http-client-auth/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-auth)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

[English](README.md) | Русский

Библиотека подставляет в исходящие HTTP-запросы токен доступа, выданный сервисом IAM. Токен запрашивается по паре «идентификатор ключа + секретный ключ», кешируется и обновляется автоматически — вызывающему коду не нужно ничего знать про время жизни токена и повторные попытки.

Подходит, когда сервис требует заголовок `Authorization: Bearer <token>`, а токен выдаёт IAM. Работает и с [httpx](https://www.python-httpx.org/) напрямую, и с [HTTP-клиентом](https://github.com/cloud-ru-tech/qa-libraries/blob/master/packages/http-client/README.ru.md).

- [Установка](#установка)
- [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
- [Быстрый старт](#быстрый-старт)
  - [Синхронный клиент](#синхронный-клиент)
  - [Асинхронный клиент](#асинхронный-клиент)
  - [Авторизация через OpenID](#авторизация-через-openid)
  - [Закрытие клиентов](#закрытие-клиентов)
  - [Своё хранилище токенов](#своё-хранилище-токенов)
  - [Логирование](#логирование)
- [Компоненты](#компоненты)
- [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-http-client-auth
```

Библиотека импортируется как модуль `http_client_auth`.

## Скиллы для AI-агентов

В пакет включён скилл [`http-client-auth-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-auth-usage/SKILL.md)
с примерами и правилами использования библиотеки для AI-агентов. Установите библиотеку
в окружение своего проекта, затем из его корня выполните (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-auth-usage --yes
```

Для Claude Code добавьте `--claude`. Инструкции поставляются вместе с версией библиотеки.

## Быстрый старт

### Синхронный клиент

```python
import httpx
from http_client import HttpClient, options
from http_client_auth import IAM_Auth, IAM_HttpClient

iam_client = IAM_HttpClient("https://iam.example.com")
auth = IAM_Auth("your_key_id", "your_key_secret", iam_client)

# С httpx напрямую
response = httpx.get("https://api.example.com/data", auth=auth)

# С http-client
client = HttpClient("https://api.example.com", options.with_auth(auth))
response = client.get("/data")
```

### Асинхронный клиент

```python
import httpx
from http_client import AsyncHttpClient, options
from http_client_auth import IAM_AsyncAuth, IAM_AsyncHttpClient

iam_client = IAM_AsyncHttpClient("https://iam.example.com")
auth = IAM_AsyncAuth("your_key_id", "your_key_secret", iam_client)

# С httpx напрямую
async with httpx.AsyncClient(auth=auth) as client:
    response = await client.get("https://api.example.com/data")

# С http-client
client = AsyncHttpClient("https://api.example.com", options.with_auth(auth))
response = await client.get("/data")
```

### Авторизация через OpenID

Достаточно взять другой клиент IAM, всё остальное не меняется:

```python
from http_client_auth import IAM_Auth, IAM_OpenID_HttpClient

iam_client = IAM_OpenID_HttpClient("https://iam.example.com")
auth = IAM_Auth("your_key_id", "your_key_secret", iam_client)
```

### Закрытие клиентов

Клиент IAM держит собственный пул соединений и закрывается вызывающим кодом — `IAM_Auth` им не владеет:

```python
with IAM_HttpClient("https://iam.example.com") as iam_client:
    auth = IAM_Auth("your_key_id", "your_key_secret", iam_client)
    with HttpClient("https://api.example.com", options.with_auth(auth)) as client:
        response = client.get("/data")
```

Для долгоживущего клиента вызывайте `close()`, для асинхронного — `await aclose()`.

### Своё хранилище токенов

По умолчанию токены лежат в памяти процесса. Чтобы переиспользовать их между процессами, реализуйте `AuthStore`:

```python
import json
from datetime import datetime

from http_client_auth import AuthStore, IAM_Auth, IAM_HttpClient, Token


class RedisAuthStore(AuthStore):
    def __init__(self, redis_client):
        self._redis = redis_client

    def get(self, key: str) -> Token | None:
        raw = self._redis.get(f"token_for:{key}")
        if raw is None:
            return None
        data = json.loads(raw)
        return Token(data["access_token"], datetime.fromisoformat(data["expires_at"]))

    def set(self, key: str, token: Token) -> None:
        self._redis.set(
            f"token_for:{key}",
            json.dumps(
                {
                    "access_token": token.access_token,
                    "expires_at": token.expires_at.isoformat(),
                }
            ),
        )


iam_client = IAM_HttpClient("https://iam.example.com")
auth = IAM_Auth("your_key_id", "your_key_secret", iam_client, store=RedisAuthStore(redis_client))
```

`IAM_AsyncAuth` принимает `AsyncAuthStore` — тот же интерфейс с асинхронными `get` и `set`:

```python
from http_client_auth import AsyncAuthStore, Token


class RedisAsyncAuthStore(AsyncAuthStore):
    def __init__(self, redis_client):
        self._redis = redis_client

    async def get(self, key: str) -> Token | None: ...

    async def set(self, key: str, token: Token) -> None: ...
```

### Логирование

Если навешиваете на клиент IAM логирование, передайте `IAM_SANITIZE_KEYS` — иначе секретный ключ из запроса OpenID и JWT из ответа попадут в лог целиком: список маскирования http-client по умолчанию их не покрывает.

```python
import logging

from http_client import options
from http_client_auth import IAM_SANITIZE_KEYS, IAM_OpenID_HttpClient

iam_client = IAM_OpenID_HttpClient(
    "https://iam.example.com",
    options.with_logger(logging.getLogger("iam"), sanitize_keys=IAM_SANITIZE_KEYS),
)
```

## Компоненты

Авторизация:

| Класс | Назначение |
|---|---|
| `IAM_Auth` | авторизация для синхронных запросов, реализует `httpx.Auth` |
| `IAM_AsyncAuth` | то же для асинхронных запросов |

Клиенты IAM — передаются в объект авторизации первым аргументом после ключей:

| Класс | Назначение |
|---|---|
| `IAM_HttpClient` | публичное API IAM |
| `IAM_AsyncHttpClient` | публичное API IAM, асинхронный |
| `IAM_OpenID_HttpClient` | API OpenID |
| `IAM_OpenID_AsyncHttpClient` | API OpenID, асинхронный |

Хранилища токенов:

| Класс | Назначение |
|---|---|
| `AuthStore` | интерфейс синхронного хранилища |
| `AsyncAuthStore` | интерфейс асинхронного хранилища |
| `InMemoryAuthStore` | хранилище в памяти, по умолчанию в `IAM_Auth` |
| `InMemoryAsyncAuthStore` | хранилище в памяти, по умолчанию в `IAM_AsyncAuth` |
| `Token` | токен доступа и время его истечения |

Прочее:

| Имя | Назначение |
|---|---|
| `AuthData` | ответ IAM: токен доступа, срок жизни, `id_token` |
| `IAM_SANITIZE_KEYS` | ключи секретов IAM для `options.with_logger(sanitize_keys=...)` |

Исключения:

| Класс | Когда возникает |
|---|---|
| `IAM_Error` | базовый класс, ловит любую ошибку авторизации |
| `IAM_AuthError` | сервис IAM ответил неуспешным кодом |
| `IAM_InvalidJsonResponseError` | ответ IAM не удалось разобрать |

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                         # зависимости всех библиотек строго по uv.lock
make test-http-client-auth        # тесты этой библиотеки
make typecheck-http-client-auth   # mypy для этой библиотеки
make check                        # форматирование, ruff, mypy и тесты всего набора
```

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-http-client-auth PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `http-client-auth/v<версия>`. Версия в теге должна совпадать
с версией в `packages/http-client-auth/pyproject.toml`.
