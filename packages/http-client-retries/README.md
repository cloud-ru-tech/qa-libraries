# http-client-retries

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-retries)](https://pypi.org/project/cloudru-qa-http-client-retries/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-retries)](https://pypi.org/project/cloudru-qa-http-client-retries/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-retries)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Повторные попытки HTTP-запросов для библиотеки [`cloudru-qa-http-client`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/http-client).

Сетевые сбои, таймауты и временные ошибки сервера — обычное дело при обращении к внешним сервисам.
Эта библиотека берёт повторы на себя: подключается к клиенту одной опцией и дальше сама переотправляет
запросы по заданной политике. Писать циклы с задержками вручную не нужно.

Работает с синхронными и асинхронными клиентами, с обычными и потоковыми запросами.
Построена на [`tenacity`](https://tenacity.readthedocs.io/), поэтому стратегии остановки и ожидания
берутся оттуда.

- [Установка](#установка)
- [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
- [Быстрый старт](#быстрый-старт)
- [Когда повторять запрос](#когда-повторять-запрос)
  - [При ошибках соединения](#при-ошибках-соединения)
  - [Ограничение: тело запроса должно быть воспроизводимым](#ограничение-тело-запроса-должно-быть-воспроизводимым)
  - [По условию на ответ](#по-условию-на-ответ)
  - [Потоковые запросы](#потоковые-запросы)
- [Настройка политики повторов](#настройка-политики-повторов)
  - [Глобально](#глобально)
  - [Для отдельного клиента](#для-отдельного-клиента)
  - [Заголовок Retry-After](#заголовок-retry-after)
- [Что происходит после последней попытки](#что-происходит-после-последней-попытки)
- [Логирование повторов](#логирование-повторов)
- [Идентификаторы запроса](#идентификаторы-запроса)
- [Повторы для произвольных функций](#повторы-для-произвольных-функций)
- [Справочник параметров](#справочник-параметров)
- [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-http-client-retries
```

Библиотека импортируется как модуль `http_client_retries`.

## Скиллы для AI-агентов

В пакет включён скилл [`http-client-retries-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-retries-usage/SKILL.md)
с примерами и правилами использования библиотеки для AI-агентов. Установите библиотеку
в окружение своего проекта, затем из его корня выполните (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-retries-usage --yes
```

Для Claude Code добавьте `--claude`. Инструкции поставляются вместе с версией библиотеки.

## Быстрый старт

Добавьте опцию в конструктор клиента — дальше все запросы этого клиента будут повторяться при сбоях:

```python
from http_client import HttpClient
from http_client_retries import options

with HttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    response = client.get("/orders/42")
```

С асинхронным клиентом всё то же самое:

```python
from http_client import AsyncHttpClient

async with AsyncHttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    response = await client.get("/orders/42")
```

## Когда повторять запрос

### При ошибках соединения

`with_retries_failed_requests` повторяет запрос, если до сервера не удалось достучаться:

```python
from http_client import HttpClient
from http_client_retries import options

client = HttpClient("https://api.example.com", options.with_retries_failed_requests())
```

Повторяются `httpx.RequestError` (включая таймауты и обрывы соединения), `httpcore.NetworkError`
и `httpcore.PoolTimeout`. Остальные ошибки пробрасываются сразу, без повторов.

Из этого списка исключены ошибки, результат которых от повтора не изменится, — иначе они впустую
съедали бы весь бюджет попыток вместе с паузами:

- `httpx.TooManyRedirects` — повтор пойдёт по той же цепочке редиректов;
- `httpx.UnsupportedProtocol` — схема URL не изменится;
- `httpx.DecodingError` — сервер вернёт то же нечитаемое тело.

> **Повторы не ограничены идемпотентными методами.** `POST` и `PATCH` повторяются наравне
> с `GET`. Сетевая ошибка не доказывает, что сервер не выполнил операцию: запрос мог дойти,
> а оборваться могло получение ответа. Одинаковый `X-Request-ID` на всех попытках защищает
> от дублей, только если сервер сам реализует такую семантику.

### Ограничение: тело запроса должно быть воспроизводимым

Повтор переотправляет тот же запрос, поэтому его тело должно читаться заново.

| Тело запроса | Повторяется |
|---|---|
| `bytes`, `str`, `json=`, `data=` | да |
| список или кортеж кусков | да |
| открытый файл | да, позиция восстанавливается перед каждой попыткой |
| `files=` с байтами или перематываемыми файлами | да |
| `files=` с неперематываемым файлом | нет |
| генератор, свой одноразовый поток | нет |

Если тело переотправить нельзя, запрос выполняется **ровно один раз** и наружу идёт исходная
ошибка. Библиотека предпочитает отдать ошибку, а не отправить на сервер обрезанное тело.

```python
def stream_document():
    yield from produce_chunks()


client.send(client.client.build_request("POST", "/documents", content=stream_document()))
```

Если такую загрузку нужно повторять, соберите тело в память (`content=b"".join(...)`) или
передайте файловый объект.

Условие из `with_retries_if` для таких запросов всё равно вычисляется — один раз. Но повторить
запрос нельзя, поэтому ответ возвращается вызывающему как есть, даже если условие просило повтор.

### По условию на ответ

`with_retries_if` повторяет запрос, пока ваше условие возвращает `True`:

```python
from httpx import Response


def is_throttled(response: Response) -> bool:
    return response.status_code == 429


client = HttpClient("https://api.example.com", options.with_retries_if(is_throttled))
```

Условие — любая функция, принимающая `httpx.Response` и возвращающая `bool`.

Опции можно комбинировать между собой и с опциями самого `http_client`:

```python
from http_client import options as http_options

client = HttpClient(
    "https://api.example.com",
    options.with_retries_failed_requests(),
    options.with_retries_if(lambda response: response.status_code >= 500),
    http_options.with_timeout(5.0),
)
```

Обе опции работают в одном цикле повторов с общим бюджетом попыток: при `stop_after_attempt(5)`
запрос уйдёт на сервер не больше пяти раз, независимо от того, чередуются ли сетевые сбои
с ответами 5xx. Порядок опций на результат не влияет.

Параметры политики при этом задаются один раз на клиента: каждый указывается ровно в одной опции.
Если один и тот же параметр задан в обеих, конструктор упадёт с `ValueError`. Библиотека
намеренно не пытается сравнивать значения по смыслу — у стратегий tenacity нет сравнения,
и «одинаковые» функции-хуки иначе молча теряли бы одну из них.

### Потоковые запросы

Отдельно ничего подключать не нужно: обе опции покрывают и `client.stream(...)`,
и `client.stream_request(...)`.

```python
with HttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    with client.stream("GET", "/large-file.zip") as response:
        for chunk in response.iter_bytes(chunk_size=8192):
            handle(chunk)
```

Условие из `with_retries_if` проверяется на открытом потоке, до чтения тела ответа.

Повторяется только **открытие** потока. Если соединение оборвалось уже во время чтения тела —
внутри `iter_bytes()` или `aiter_bytes()` — ошибка выходит наружу сразу, без повторов: часть данных
вы уже получили, и начинать заново было бы небезопасно. Докачку с середины нужно организовывать
самостоятельно, через заголовок `Range`.

## Настройка политики повторов

### Глобально

`configure` задаёт умолчания для всего процесса:

```python
from http_client_retries import Config

from http_client_retries import configure
from tenacity import stop_after_attempt, wait_exponential_jitter

configure(
    options=Config(
        stop=stop_after_attempt(5), wait=wait_exponential_jitter(initial=1, max=64, jitter=1), reraise=False
    ),
)
```

Без вызова `configure` действуют значения из [справочника параметров](#справочник-параметров):
до 5 попыток с экспоненциально растущей паузой и случайным разбросом.

Стратегии берутся из tenacity — см.
[stop](https://tenacity.readthedocs.io/en/stable/api.html#stop-functions) и
[wait](https://tenacity.readthedocs.io/en/stable/api.html#wait-functions).

### Для отдельного клиента

Если одному клиенту нужна своя политика, передайте её прямо в опцию:

```python
from http_client_retries import RetryOverrides

from tenacity import stop_after_attempt

payments = HttpClient(
    "https://payments.internal",
    options.with_retries_failed_requests(
        overrides=RetryOverrides(stop=stop_after_attempt(2), reraise=True),
    ),
)

catalog = HttpClient(
    "https://catalog.internal",
    options.with_retries_failed_requests(),
)
```

Здесь `payments` сделает не больше двух попыток, а `catalog` будет жить по глобальной конфигурации.
Параметры, которые вы не указали, тоже берутся из глобальной — включая изменения, сделанные
`configure` уже после создания клиента.

### Заголовок Retry-After

Если сервер прислал `Retry-After` (обычно вместе с 429 или 503), пауза берётся из этого заголовка.
Понимаются оба формата — число секунд и HTTP-дата. Значение ограничено сверху параметром
`max_retry_after`. Нечитаемый заголовок игнорируется: работает обычная стратегия ожидания.

Заголовок приходит в ответе, поэтому учесть его может только политика, которая умеет повторять
по ответу. У клиента, где включены **лишь** повторы по сетевым ошибкам, `respect_retry_after`
и `max_retry_after` ни на что не влияют.

Выключается глобально или для отдельного клиента:

```python
from http_client_retries import Config, RetryOverrides

configure(options=Config(respect_retry_after=False))

client = HttpClient(
    "https://api.example.com", options.with_retries_failed_requests(overrides=RetryOverrides(respect_retry_after=False))
)
```

## Что происходит после последней попытки

Когда попытки исчерпаны, поведение зависит от `reraise`:

| `reraise` | Что возбуждается |
|---|---|
| `False` (по умолчанию) | `tenacity.RetryError`; исходная ошибка доступна через `err.last_attempt.exception()` |
| `True` | сама исходная ошибка, например `httpx.ConnectError` |

```python
from tenacity import RetryError

try:
    response = client.get("/orders/42")
except RetryError as err:
    original = err.last_attempt.exception()
```

Вариант с `reraise=True` удобен, когда вызывающий код уже умеет обрабатывать исключения `httpx`:

```python
from http_client_retries import RetryOverrides

import httpx

client = HttpClient(
    "https://api.example.com", options.with_retries_failed_requests(overrides=RetryOverrides(reraise=True))
)

try:
    response = client.get("/orders/42")
except httpx.ConnectError:
    ...
```

## Логирование повторов

`log_retry_error_hook` пишет в лог причину каждого повтора — метод, URL и ошибку:

```python
from http_client_retries import Config

import logging

from http_client_retries import configure, log_retry_error_hook

configure(options=Config(before_sleep_hook=log_retry_error_hook(logging.getLogger("http"))))
```

Вместо него можно поставить свою функцию — она получает
[`RetryCallState`](https://tenacity.readthedocs.io/en/stable/api.html#tenacity.RetryCallState):

```python
from http_client_retries import Config


def report_attempt(retry_state):
    metrics.increment("http.retry", attempt=retry_state.attempt_number)


configure(options=Config(before_sleep_hook=report_attempt))
```

Асинхронный хук можно поставить только асинхронному клиенту: синхронный `tenacity` не станет его
ожидать, поэтому такая связка отвергается с `TypeError` вместо тихого пропуска вызовов.

Хук можно отключить для отдельного клиента, передав `before_sleep_hook=None` прямо в опцию, —
глобальная настройка при этом не меняется.

## Идентификаторы запроса

Все попытки одного запроса уходят с одним и тем же `X-Request-ID` и `Traceparent` — повторы можно
найти в логах по общему идентификатору, а сервер может опираться на него для защиты от дублей.
Ничего настраивать не нужно:

```python
client = HttpClient(
    "https://api.example.com",
    http_options.with_autogenerated_request_id(),
    options.with_retries_failed_requests(),
)
```

Идентификатор, выставленный вызывающим кодом вручную, тоже сохраняется между попытками.

Правило простое: **идентификатор принадлежит объекту запроса**. Разные запросы получают разные
значения; все отправки одного `httpx.Request` — включая повторы — идут под одним.

Отсюда одно ограничение. Штатные схемы аутентификации httpx (`BasicAuth`, `DigestAuth`, функция)
переиспользуют объект запроса, поэтому идентификатор сохраняется. Но своя `httpx.Auth`, которая
конструирует **новый** `Request` вместо изменения исходного, получит новый идентификатор на каждой
попытке — переносить заголовки в порождённый запрос библиотека не берётся. Если сервер полагается
на `X-Request-ID` для защиты от дублей, в такой схеме проставляйте заголовок сами.

## Повторы для произвольных функций

Если нужно повторять вызов, не связанный с `http_client`, используйте декораторы напрямую.

`retry_if_failed` — повтор при ошибках соединения:

```python
import httpx

from http_client_retries import retry_if_failed


@retry_if_failed
def fetch_status():
    return httpx.get("https://api.example.com/health")
```

`retry_if` — повтор по условию на результат:

```python
from http_client_retries import retry_if


@retry_if(lambda response: response.status_code == 503)
def fetch_report():
    return httpx.get("https://api.example.com/report")
```

Оба работают и с асинхронными функциями:

```python
@retry_if_failed
async def fetch_status():
    async with httpx.AsyncClient() as client:
        return await client.get("https://api.example.com/health")
```

Декораторы используют глобальную конфигурацию из `configure`.

## Справочник параметров

Принимаются и функцией `configure`, и обеими опциями.

| Параметр | По умолчанию | Назначение |
|---|---|---|
| `stop` | `stop_after_attempt(5)` | когда прекратить попытки |
| `wait` | `wait_exponential_jitter(initial=1, max=64, jitter=1)` | пауза между попытками |
| `before_sleep_hook` | `None` | функция, вызываемая перед каждым повтором |
| `reraise` | `False` | возбуждать исходную ошибку вместо `RetryError`; на повторы по условию не влияет |
| `respect_retry_after` | `True` | брать паузу из заголовка `Retry-After`; нужна политика с повтором по ответу |
| `max_retry_after` | `60.0` | верхняя граница паузы из `Retry-After`, в секундах |

`get_config()` отдаёт неизменяемый снимок: подменить у него поле нельзя, а `configure()` заменяет
конфигурацию целиком одним присваиванием. Неизменяемость поверхностная — сами стратегии tenacity
остаются обычными изменяемыми объектами, поэтому не меняйте их поля после передачи в `configure()`,
а собирайте новую стратегию.

`reraise` действует только для повторов по сетевым ошибкам: там есть исходное исключение, которое
можно возбудить заново. Когда попытки исчерпаны на условии по ответу, возбуждать нечего — всегда
будет `RetryError`, а последний ответ доступен через `err.last_attempt.result()`.

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                            # зависимости всех библиотек строго по uv.lock
make test-http-client-retries        # тесты этой библиотеки
make typecheck-http-client-retries   # mypy для этой библиотеки
make check                           # форматирование, ruff, mypy и тесты всего набора
```

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-http-client-retries PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `http-client-retries/v<версия>`. Версия в теге должна совпадать
с версией в `packages/http-client-retries/pyproject.toml`.
