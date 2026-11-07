# Объекты ответов на запросы HTTP-клиента

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-responses)](https://pypi.org/project/cloudru-qa-http-client-responses/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-responses)](https://pypi.org/project/cloudru-qa-http-client-responses/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-responses)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Обёртки над `httpx.Response`, которые знают, во что разбирать тело ответа.

Метод клиента возвращает не голый `Response`, из которого потом руками достают JSON, а объект с типом ожидаемых данных. Тип виден в сигнатуре метода, разбор вызывается одной строкой, а IDE и mypy подсказывают поля модели.

- [Объекты ответов на запросы HTTP-клиента](#объекты-ответов-на-запросы-http-клиента)
  - [Установка](#установка)
  - [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
  - [Использование](#использование)
    - [Атрибуты ответа](#атрибуты-ответа)
    - [Ошибки разбора](#ошибки-разбора)
    - [Асинхронные клиенты](#асинхронные-клиенты)
  - [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-http-client-responses
```

Библиотека импортируется как модуль `http_client_responses`.

## Скиллы для AI-агентов

В пакет включён скилл [`http-client-responses-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-responses-usage/SKILL.md)
с примерами и правилами использования библиотеки для AI-агентов. Установите библиотеку
в окружение своего проекта, затем из его корня выполните (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-responses-usage --yes
```

Для Claude Code добавьте `--claude`. Инструкции поставляются вместе с версией библиотеки.

## Использование

- `JsonResponse[PydanticModel]` — тело ответа описано pydantic моделью. Вместо `PydanticModel` укажите свою модель.
- `GenericResponse[ReturnType]` — тело разбирает переданная функция.
- `ResponseWrapper` — без разбора тела, если нужны только статус, заголовки и содержимое.

```python
from http_client import HttpClient
from httpx import Response
from pydantic import BaseModel
from http_client_responses import GenericResponse, JsonResponse


class ExampleRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    search: str | None = None


class User(BaseModel):
    name: str
    age: int
    alive: bool
    skills: list[str]


class ExampleResponse(BaseModel):
    users: list[User]
    total: int


class ExampleClient(HttpClient):
    """Тестовый HTTP-клиент."""

    def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        """Отправить простой get запрос на получение списка пользователей в JSON формате."""
        response = self.get(
            url="/users",
            params=request.model_dump(exclude_none=True),
        )
        return JsonResponse(
            response=response,
            schema=ExampleResponse,
        )

    def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        """Отправить запрос, получающий строковые данные, которые будут преобразованы в dict."""
        response = self.get(f"/user/{user_id}/details")

        def parser(r: Response) -> dict[str, str]:
            result = dict()
            for line in r.text.split("\n"):
                key, value = line.split(":", maxsplit=1)
                result[key] = value.strip()
            return result

        return GenericResponse(
            response=response,
            parser=parser,
        )
```

Разбор тела вызывается явно: `model()` у `JsonResponse`, `parse()` у `GenericResponse`.

```python
response = client.get_users(ExampleRequest(limit=10))

assert response.status_code == 200
assert response.model().total == 42
```

`raise_for_status()` возвращает саму обёртку, поэтому проверку статуса удобно ставить в цепочку:

```python
users = client.get_users(ExampleRequest()).raise_for_status().model()
```

### Атрибуты ответа

| Атрибут | Тип | Комментарий |
|---|---|---|
| `status_code` | `int` | |
| `reason_phrase` | `str` | |
| `headers` | `httpx.Headers` | `get_list()` отдаёт все значения повторяющегося заголовка |
| `raw_headers` | `dict[str, str]` | по одному значению на заголовок |
| `cookies` | `httpx.Cookies` | |
| `content` / `text` | `bytes` / `str` | |
| `url` | `str` | |
| `request` | `httpx.Request` | |
| `elapsed` | `timedelta` | |
| `is_success` / `is_error` | `bool` | |
| `is_client_error` / `is_server_error` | `bool` | 4xx / 5xx |
| `raise_for_status()` | `Self` | бросает `httpx.HTTPStatusError` на любой не-2xx статус |
| `json()` | `Any` | разбор тела как JSON без валидации схемы |

Для `Set-Cookie` и других заголовков, которые приходят по нескольку раз, берите `headers.get_list("set-cookie")`.

### Ошибки разбора

Если тело не удалось разобрать, вместо голого `pydantic.ValidationError` бросается `ResponseParseError` — по нему сразу видно, какой запрос упал и что ответил сервер:

```
ResponseParseError: не удалось разобрать тело ответа
  GET http://test.com/users -> 200
  Body: {"users": [{"name": "John Doe"}], "total": "много"}
  Причина: 1 validation error for ExampleResponse
  total
    Input should be a valid integer, unable to parse string as an integer
```

Исходное исключение доступно в `error.cause` и в `__cause__`.

### Асинхронные клиенты

```python
from http_client import AsyncHttpClient


class AsyncExampleClient(AsyncHttpClient):
    async def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        response = await self.get(url="/users", params=request.model_dump(exclude_none=True))
        return JsonResponse(response=response, schema=ExampleResponse)
```

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                              # зависимости всех библиотек строго по uv.lock
make test-http-client-responses        # тесты этой библиотеки
make typecheck-http-client-responses   # mypy для этой библиотеки
make check                             # форматирование, ruff, mypy и тесты всего набора
```

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-http-client-responses PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `http-client-responses/v<версия>`. Версия в теге должна совпадать
с версией в `packages/http-client-responses/pyproject.toml`.
