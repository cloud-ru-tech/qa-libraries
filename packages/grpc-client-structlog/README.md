# Структурированные логи для gRPC-клиента

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-grpc-client-structlog)](https://pypi.org/project/cloudru-qa-grpc-client-structlog/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-grpc-client-structlog)](https://pypi.org/project/cloudru-qa-grpc-client-structlog/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-grpc-client-structlog)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Опция `with_structlogger` для [gRPC-клиента](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client),
которая пишет все запросы и ответы через [structlog](https://www.structlog.org/en/stable/index.html).

Штатный логгер grpc-client складывает запрос в одну текстовую строку. Здесь метод, тело,
метаданные и статус уходят в лог отдельными полями — их видно в консоли при отладке и по ним
можно искать и фильтровать в собранных логах.

- [Установка](#установка)
- [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
- [Использование](#использование)
- [Асинхронный клиент](#асинхронный-клиент)
- [Поля лога](#поля-лога)
- [Маскирование секретов](#маскирование-секретов)
- [Параметры](#параметры)
- [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-grpc-client-structlog
```

Библиотека импортируется как модуль `grpc_client_structlog`. Подходящая версия
[`cloudru-qa-grpc-client`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client)
устанавливается вместе с ней.

## Скиллы для AI-агентов

В пакет включён скилл [`grpc-client-structlog-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/grpc-client-structlog-usage/SKILL.md)
с примерами и правилами использования библиотеки для AI-агентов. Установите библиотеку
в окружение своего проекта, затем из его корня выполните (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill grpc-client-structlog-usage --yes
```

Для Claude Code добавьте `--claude`. Инструкции поставляются вместе с версией библиотеки.

## Использование

Передайте опцию в конструктор клиента — дальше логируется всё само:

```python
import structlog

from grpc_client import GRPCClient
from grpc_client_structlog import with_structlogger

from api import orders_pb2, orders_pb2_grpc


class OrdersClient(GRPCClient[orders_pb2_grpc.OrdersStub]):
    @property
    def stub_class(self):
        return orders_pb2_grpc.OrdersStub

    def get_order(self, order_id: str):
        return self.send_unary_unary_request(orders_pb2.GetOrderRequest(id=order_id), self.stub.GetOrder)


with OrdersClient.from_addr(
    "orders.example.com:443",
    with_structlogger(structlog.get_logger("orders")),
) as client:
    client.get_order("42")
```

Запрос попадёт в лог событием `grpc request sent`, ответ — `grpc response received`.
Общее поле `trace_id` связывает их между собой.

## Асинхронный клиент

Опция та же, ничего дополнительно настраивать не нужно: нужный интерцептор выбирается
по типу клиента:

```python
from grpc_client import AsyncGRPCClient


class AsyncOrdersClient(AsyncGRPCClient[orders_pb2_grpc.OrdersStub]):
    @property
    def stub_class(self):
        return orders_pb2_grpc.OrdersStub

    async def get_order(self, order_id: str):
        return await self.send_unary_unary_request(orders_pb2.GetOrderRequest(id=order_id), self.stub.GetOrder)


async with AsyncOrdersClient.from_addr("orders.example.com:443", with_structlogger(logger)) as client:
    await client.get_order("42")
```

Итоговая запись о потоке ответных сообщений пишется отдельной задачей, поэтому асинхронный
клиент нужно закрывать: `close()` дожидается таких задач.

## Поля лога

До двух записей на вызов, связанных общим `trace_id`: запрос и ответ.

| Поле | Событие | Значение |
|---|---|---|
| `method` | оба | полное имя метода вида `/package.Service/Method` |
| `body` | оба | тело сообщения в виде JSON-строки; у ответа — только у успешного унарного вызова |
| `metadata` | оба | метаданные в виде JSON-строки; поля нет, если метаданных не было |
| `status_code` | ответ | имя кода статуса: `OK`, `NOT_FOUND`, … |
| `details` | ответ | текст ошибки от сервиса; поле есть только у неуспешного вызова |
| `messages_count` | ответ | количество сообщений, полученных из потока; поле есть только у потоковых вызовов |
| `trace_id` | оба | UUID4, сгенерированный на запрос |

В `status_code` пишется **имя** кода, а не его номер. Имя читается без справочника и по нему
удобно фильтровать записи; номер добавил бы в поле второе значение, и искать по строке
`5 (NOT_FOUND)` пришлось бы подстрокой.

Составные значения — `body` и `metadata` — попадают в лог уже сериализованными в JSON-строку,
а не вложенными структурами: иначе их поля смешивались бы с полями контекста приложения.

Тело потока в лог не попадает — ни запросов, ни ответов: вычитывание потока ради лога изменило бы
поведение вызова. У запроса-потока в `body` стоит `<streamed content>`, а о потоке ответов
пишется итоговый статус и `messages_count`.

Длинное тело обрезается: по умолчанию — по 4096 символов, дальше в `body` дописывается
`... <обрезано>`. Предел задаётся параметром `payload_maxlength`. Если тело не удалось подготовить —
например, из-за неверного glom-пути в `sanitize_keys` — в `body` попадёт
`<не удалось подготовить тело сообщения>`, а сам запрос всё равно уйдёт: лог собирается так,
чтобы не ронять вызов.

## Маскирование секретов

Поля с типовыми именами секретов маскируются **по умолчанию и на любой глубине**, включая
вложенные сообщения и элементы массивов:

`authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, `api-key`, `api_key`,
`access_token`, `refresh_token`, `password`, `secret`, `token`.

Имя сравнивается без учёта стиля записи, поэтому `accessToken` в теле сообщения тоже будет скрыт.

Свои поля добавляйте через `sanitize_keys`. Ключ без разделителей считается именем поля
и маскируется на любом уровне вложенности, ключ с точкой, звёздочкой или скобками — путём
[glom](https://glom.readthedocs.io/en/latest/):

```python
with_structlogger(
    logger,
    sanitize_keys=["x-tenant-key", "user.internal_id", "items.*.card_number"],
)
```

Отключить список по умолчанию можно только явно: `use_default_sanitize_keys=False`.

Маскирование не трогает само сообщение: `****` существует только в логе.

Поле `details` — текст ошибки от сервиса — не маскируется и не обрезается: это свободная строка,
а маскирование работает по именам полей и путям. Если сервис кладёт в статус что-то
конфиденциальное, оно попадёт в лог как есть. Так же ведёт себя штатная `options.with_logger`.

## Параметры

| Параметр | Тип | Назначение |
|---|---|---|
| `logger` | `BoundLogger \| FilteringBoundLogger` | куда писать |
| `sanitize_keys` | `Sequence[str] \| None` | имена полей и glom-пути, значения которых заменяются на `****` |
| `json_indent` | `int \| None` | ширина отступа при сериализации JSON-свойств |
| `log_level` | `int \| None` | уровень успешной записи, по умолчанию `INFO` |
| `err_log_level` | `int \| None` | уровень записи о неуспешном вызове, по умолчанию `ERROR` |
| `payload_maxlength` | `int \| None` | предел длины тела в логе, по умолчанию 4096 символов |
| `use_default_sanitize_keys` | `bool` | маскировать ли типовые секреты на любой глубине, по умолчанию `True` |

Уровни, отступ и предел длины тела можно задать сразу для всего проекта вызовом
`grpc_client.configure_logging(...)`. То, что передали в `with_structlogger`, важнее общей настройки.

Переменные окружения `GRPC_CLIENT_*` сами по себе ничего не меняют: их читает `configure_logging(...)`
в момент вызова. Без этого вызова значения остаются библиотечными по умолчанию.

`log_level` и `err_log_level` принимают только `DEBUG`, `INFO`, `WARNING`, `ERROR` и `CRITICAL`:
bound-логгер structlog выбирает метод по имени уровня, а имена есть только у этих пяти.
Промежуточное значение вроде `15` даст `ValueError` сразу, а не на первом запросе.

Уровень фильтрует сам structlog: если порог logger-а выше, чем `log_level`, запись не дойдёт
до вывода, и опция будет выглядеть сломанной.

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                               # зависимости всех библиотек строго по uv.lock
make test-grpc-client-structlog         # тесты этой библиотеки
make typecheck-grpc-client-structlog    # mypy для этой библиотеки
make check                              # форматирование, ruff, mypy и тесты всего набора
```

Тестам нужен запущенный Docker: gRPC сервис поднимается контейнером из `tests/docker-compose.yml`,
образ собирается при первом прогоне. Если сервис уже поднят, контейнер можно не запускать —
достаточно передать его адрес:

```shell
uv run --no-sync python packages/grpc-client-structlog/tests/service.py &
SERVICE_ADDR=localhost:50051 make test-grpc-client-structlog
```

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-grpc-client-structlog PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `grpc-client-structlog/v<версия>`. Версия в теге должна совпадать
с версией в `packages/grpc-client-structlog/pyproject.toml`.
