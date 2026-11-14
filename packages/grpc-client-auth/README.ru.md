# Авторизация для gRPC-клиента

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-grpc-client-auth)](https://pypi.org/project/cloudru-qa-grpc-client-auth/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-grpc-client-auth)](https://pypi.org/project/cloudru-qa-grpc-client-auth/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-grpc-client-auth)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

[English](README.md) | Русский

Получение и обновление токенов доступа IAM для [gRPC-клиента](https://github.com/cloud-ru-tech/qa-libraries/blob/master/packages/grpc-client/README.ru.md).

- [Авторизация для gRPC-клиента](#авторизация-для-grpc-клиента)
  - [Установка](#установка)
  - [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
  - [Использование](#использование)
    - [Синхронный клиент](#синхронный-клиент)
    - [Асинхронный клиент](#асинхронный-клиент)
    - [Что делает библиотека](#что-делает-библиотека)
    - [Хранилище токенов](#хранилище-токенов)
    - [Маскирование секретов в логах](#маскирование-секретов-в-логах)
    - [Компоненты](#компоненты)
  - [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-grpc-client-auth
```

Библиотека импортируется как модуль `grpc_client_auth`.

## Скиллы для AI-агентов

У этой библиотеки собственного скилла пока нет. Если в проекте установлены другие
библиотеки набора со [скиллами для AI-агентов](https://github.com/cloud-ru-tech/qa-libraries/blob/master/README.ru.md#скиллы-для-ai-агентов),
выбрать и подключить их можно из корня проекта (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

Для Claude Code добавьте `--claude`.

## Использование

### Синхронный клиент

```python
from grpc_client import options
from grpc_client_auth import IAM_GrpcAuth, IAM_HttpClient

iam_client = IAM_HttpClient("https://iam.example.com")
client = MyGrpcClient.from_addr(
    "service.example.com:443",
    options.with_auth(IAM_GrpcAuth("my_key_id", "my_key_secret", iam_client)),
)

response = client.send_example_request(...)

client.close()
iam_client.close()
```

`IAM_GrpcAuth` реализует контракт `grpc_client.ClientAuth`, поэтому подключается штатной опцией `options.with_auth`.

### Асинхронный клиент

```python
from grpc_client import options
from grpc_client_auth import IAM_AsyncHttpClient, IAM_GrpcAsyncAuth

iam_client = IAM_AsyncHttpClient("https://iam.example.com")
client = MyAsyncGrpcClient.from_addr(
    "service.example.com:443",
    options.with_auth(IAM_GrpcAsyncAuth("my_key_id", "my_key_secret", iam_client)),
)

response = await client.send_example_request(...)

await client.close()
await iam_client.aclose()
```

### Что делает библиотека

- получает токен в IAM и хранит его до истечения срока;
- выпускает новый, когда срок истёк или сервис ответил `UNAUTHENTICATED`;
- не идёт в IAM повторно, если токен уже обновил параллельный запрос.

Подстановкой заголовка `authorization` и повтором запроса занимается сам gRPC-клиент — см. раздел «Авторизация» в его README.

Создавайте один объект авторизации на набор учётных данных и переиспользуйте его для всех клиентов: экономия обращений в IAM работает в пределах одного объекта.

Для авторизации доступны два API IAM:

| Клиент | Маршрут |
| --- | --- |
| `IAM_HttpClient`, `IAM_AsyncHttpClient` | `POST /api/v1/auth/token` |
| `IAM_OpenID_HttpClient`, `IAM_OpenID_AsyncHttpClient` | `POST /auth/system/openid/token` |

### Хранилище токенов

По умолчанию токены хранятся в памяти процесса. Если нужно разделить их между процессами, реализуйте интерфейс `AuthStore` (или `AsyncAuthStore` для асинхронного варианта):

```python
from datetime import datetime

from grpc_client_auth import AuthStore, Token


class RedisAuthStore(AuthStore):
    """Хранилище токенов в Redis."""

    def __init__(self, redis_client):
        self._redis = redis_client

    def get(self, key: str) -> Token | None:
        raw = self._redis.hgetall(f"token:{key}")
        if not raw:
            return None
        return Token(raw["access_token"], datetime.fromisoformat(raw["expires_at"]))

    def set(self, key: str, token: Token) -> None:
        self._redis.hset(
            f"token:{key}",
            mapping={
                "access_token": token.access_token,
                "expires_at": token.expires_at.isoformat(),
            },
        )


auth = IAM_GrpcAuth("my_key_id", "my_key_secret", iam_client, store=RedisAuthStore(...))
```

`Token` хранит само значение и момент, начиная с которого токен считается непригодным. Срок берётся из поля `expires_in` ответа IAM, из него вычитается небольшой запас, чтобы токен не протух в пути.

### Маскирование секретов в логах

Если HTTP-клиент IAM логирует запросы, добавьте в маскирование ключи, специфичные для IAM, — иначе секретный ключ из запроса OpenID и JWT из ответа попадут в лог целиком:

```python
from http_client import options as http_options
from grpc_client_auth import IAM_SANITIZE_KEYS, IAM_HttpClient

iam_client = IAM_HttpClient(
    "https://iam.example.com",
    http_options.with_logger(logger, sanitize_keys=IAM_SANITIZE_KEYS),
)
```

### Компоненты

HTTP-клиенты IAM, хранилище токенов и модель токена берутся из библиотеки [`cloudru-qa-http-client-auth`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/packages/http-client-auth/README.ru.md) и реэкспортируются отсюда, чтобы не приходилось держать в голове, что откуда импортируется.

Там же есть `IAM_Auth` и `IAM_AsyncAuth` — это авторизация для HTTP-клиента (`httpx.Auth`), другой контракт. Для gRPC-клиента нужны `IAM_GrpcAuth` и `IAM_GrpcAsyncAuth` из этой библиотеки.

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                          # зависимости всех библиотек строго по uv.lock
make test-grpc-client-auth         # тесты этой библиотеки
make typecheck-grpc-client-auth    # mypy для этой библиотеки
make check                         # форматирование, ruff, mypy и тесты всего набора
```

Тестам нужен запущенный Docker: контейнер с сервисом [grpcbin](https://grpcb.in/) поднимается
автоматически, а тестовый API генерируется из `proto/` перед запуском. Запросы в IAM в тестах
перехватываются через `pytest-httpx`.

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-grpc-client-auth PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `grpc-client-auth/v<версия>`. Версия в теге должна совпадать с версией
в `packages/grpc-client-auth/pyproject.toml`.
