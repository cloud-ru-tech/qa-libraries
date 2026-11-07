# Базовый gRPC-клиент

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-grpc-client)](https://pypi.org/project/cloudru-qa-grpc-client/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-grpc-client)](https://pypi.org/project/cloudru-qa-grpc-client/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-grpc-client)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Базовый клиент для отправки запросов в gRPC сервисы из автотестов.

- [Базовый gRPC-клиент](#базовый-grpc-клиент)
  - [Установка](#установка)
  - [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
  - [Использование](#использование)
    - [1. Автогенерация из proto](#1-автогенерация-из-proto)
    - [2. Написание собственного клиента](#2-написание-собственного-клиента)
    - [3. Создание клиента и опции](#3-создание-клиента-и-опции)
    - [4. Вызов методов](#4-вызов-методов)
    - [5. Работа с ответом](#5-работа-с-ответом)
    - [6. Потоки](#6-потоки)
    - [7. Параметры вызова](#7-параметры-вызова)
    - [8. Метаданные](#8-метаданные)
    - [9. Ошибки и расширенный статус](#9-ошибки-и-расширенный-статус)
    - [10. Авторизация](#10-авторизация)
    - [11. Логирование](#11-логирование)
    - [12. Асинхронный клиент](#12-асинхронный-клиент)
    - [13. Свои интерцепторы](#13-свои-интерцепторы)
  - [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-grpc-client
```

Библиотека импортируется как модуль `grpc_client`.

Если нужна ещё и генерация кода из proto-файлов, поставьте библиотеку с дополнением `codegen`:

```shell
pip install "cloudru-qa-grpc-client[codegen]"
```

## Скиллы для AI-агентов

В пакет включён скилл [`grpc-client-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/grpc-client-usage/SKILL.md)
с примерами и правилами использования библиотеки для AI-агентов. Установите библиотеку
в окружение своего проекта, затем из его корня выполните (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill grpc-client-usage --yes
```

Для Claude Code добавьте `--claude`. Инструкции поставляются вместе с версией библиотеки.

## Использование

### 1. Автогенерация из proto

Первым делом необходимо получить доступ к proto файлам с описанием контракта сервиса, для которого нужно разработать gRPC-клиент. Для этого необходимо обратиться к разработчикам сервиса. Примеры таких файлов можно посмотреть в папке [proto](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client/proto/) в данном репозитории.

Получив к ним доступ, нужно сгенерировать на их основе `pb2.py` файлы. Возможно, они уже были сгенерированы разработчиками и вынесены в какую-либо библиотеку или репозиторий — стоит уточнить.

Если код контрактов нужно генерировать самостоятельно, копируем proto файлы к себе в проект (возможно, стоит рассмотреть вариант с [git submodules](https://git-scm.com/book/ru/v2/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D1%8B-Git-%D0%9F%D0%BE%D0%B4%D0%BC%D0%BE%D0%B4%D1%83%D0%BB%D0%B8)). Далее пользуемся утилитой [`protoc`](https://grpc.io/docs/languages/python/quickstart/) из пакета `grpcio-tools`, который ставится вместе с дополнением `cloudru-qa-grpc-client[codegen]`.

ℹ️ Простой пример генерации `pb2.py` файлов можно посмотреть в скрипте [gen-test-api.sh](https://github.com/cloud-ru-tech/qa-libraries/blob/master/packages/grpc-client/gen-test-api.sh), где генерируются файлы для тестов.

### 2. Написание собственного клиента

Библиотека реализует базовые методы отправки gRPC-запросов. Чтобы использовать их, создайте свой класс клиента и унаследуйте его от `GRPCClient`, указав в параметре класс Stub-а сервиса:

```python
from typing import Type

from grpc_client import CallOptions, GRPCClient, GRPCResponse, MetadataType

# Импортируем сгенерированные на предыдущем этапе pb2.py модули
from api import example_pb2, example_pb2_grpc


class MyCustomClient(GRPCClient[example_pb2_grpc.ExampleStub]):
    """gRPC-клиент сервиса «Example»."""

    @property
    def stub_class(self) -> Type[example_pb2_grpc.ExampleStub]:
        return example_pb2_grpc.ExampleStub

    def send_example_request(
        self,
        data: example_pb2.RequestMessage,
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[example_pb2.ResponseMessage]:
        """Отправить тестовый gRPC-запрос в сервис.

        :param data: данные запроса
        :param metadata: метаданные запроса (аналог заголовков для HTTP)
        :param options: параметры вызова
        :return: объект ответа, содержащий данные ответа на запрос
        """
        return self.send_unary_unary_request(
            msg=data,
            method=self.stub.ExampleMethod,
            metadata=metadata,
            options=options,
        )
```

Разберём подробно:

1. Наследуемся от `GRPCClient` и указываем в квадратных скобках класс Stub-а — тогда `self.stub` будет типизирован.
2. В __обязательном__ свойстве `stub_class` возвращаем тот же Stub класс. Он импортируется из сгенерированных `pb2_grpc.py` модулей и называется «{имя сервиса}Stub». После этого все методы сервиса доступны в свойстве `self.stub`.
3. Для вызова конкретных запросов используем один из четырёх методов отправки базового класса (разберём далее), передавая туда данные запроса и метод из `self.stub`.

### 3. Создание клиента и опции

Клиент создаётся фабричным методом `from_addr`, которому передаются адрес сервиса и опции:

```python
import logging

from grpc_client import options

client = MyCustomClient.from_addr(
    "localhost:9000",
    options.with_insecure_channel(),
    options.with_timeout(30),
    options.with_logger(logging.getLogger("example")),
    options.with_autogenerated_request_id(),
)

response = client.send_example_request(...)
client.close()
```

⚠️ Канал, созданный клиентом, нужно закрывать. Самый простой способ — использовать клиент как контекстный менеджер:

```python
with MyCustomClient.from_addr("localhost:9000", options.with_insecure_channel()) as client:
    response = client.send_example_request(...)
```

В pytest для этого удобна фикстура:

```python
@pytest.fixture
def example_client() -> Iterator[MyCustomClient]:
    with MyCustomClient.from_addr("localhost:9000", options.with_insecure_channel()) as client:
        yield client
```

Если канал уже создан и его жизненным циклом управляет вызывающий код, используйте `from_channel` — такой канал клиент не закрывает:

```python
with grpc.insecure_channel("localhost:9000") as channel:
    client = MyCustomClient.from_channel(channel)
```

Доступные опции:

| Опция | Назначение |
| --- | --- |
| `with_timeout(timeout)` | Ограничение времени вызова по умолчанию, `None` — без ограничения |
| `with_insecure_channel()` | Незашифрованный канал (по умолчанию канал шифруется) |
| `with_ssl_credentials(credentials)` | Свои учётные данные TLS |
| `with_root_certificates(pem_bytes)` | Корневой сертификат для проверки сервера |
| `with_channel_options(options)` | Низкоуровневые настройки канала grpcio, в том числе `grpc.service_config` |
| `with_compression(compression)` | Сжатие сообщений |
| `with_default_metadata(metadata)` | Метаданные, добавляемые к каждому запросу |
| `with_auth(auth)` | Подстановка токена доступа, см. [Авторизация](#10-авторизация) |
| `with_logger(logger, ...)` | Логирование запросов и ответов |
| `with_autogenerated_request_id(key)` | Автоматический `x-request-id` |
| `with_autogenerated_traceparent(key)` | Автоматический `traceparent` по W3C Trace Context |
| `with_interceptor(*interceptors)` | Свои интерцепторы grpcio |

Порядок опций важен: интерцепторы применяются в порядке добавления. Логирование стоит подключать после авторизации, чтобы в лог попал итоговый запрос.

### 4. Вызов методов

В gRPC есть четыре вида методов:

1. Унарный запрос (**Unary**) — обычный блокирующий запрос: клиент отправляет одно сообщение серверу и получает одно в ответ.
2. Поток со стороны клиента (**Client streaming**) — клиент отправляет последовательность сообщений, а после её завершения ждёт единственный ответ.
3. Поток со стороны сервера (**Server streaming**) — клиент отправляет запрос и читает последовательность ответных сообщений.
4. Двунаправленный поток (**Bidirectional streaming**) — и клиент, и сервер отправляют последовательности сообщений независимо друг от друга.

Подробнее можно прочитать [в документации grpc.io](https://grpc.io/docs/what-is-grpc/core-concepts/).

В базовом классе реализованы все четыре:

| Метод | Тип вызова | Возвращает |
| --- | --- | --- |
| `send_unary_unary_request` | унарный | `GRPCResponse[T]` |
| `send_stream_unary_request` | поток от клиента | `GRPCResponse[T]` |
| `send_unary_stream_request` | поток от сервера | `GRPCStreamResponse[T]` |
| `send_stream_stream_request` | двунаправленный поток | `GRPCStreamResponse[T]` |

ℹ️ В python потоки запросов передаются [итератором](https://docs.python.org/3/library/stdtypes.html#iterator-types) `Iterator[Message]`. Простой итератор из списка делается функцией `iter`.

### 5. Работа с ответом

Унарные методы возвращают `GRPCResponse`:

```python
response = client.send_example_request(data)

response.status_code  # grpc.StatusCode — код статуса ответа
response.details  # str — пояснение к статусу, обычно заполняется при ошибке
response.ok  # bool — успешен ли запрос
response.message()  # ответное сообщение, бросает MessageUndefinedError, если его нет
response.initial_metadata  # метаданные до тела ответа, ближайший аналог заголовков HTTP
response.trailing_metadata  # метаданные после тела ответа
response.error  # исходный grpc.RpcError, если запрос неуспешен
response.error_status  # расширенный статус google.rpc.Status, если сервис его прислал
response.raise_for_status()  # бросить ResponseStatusError, если статус не OK
```

Ошибки gRPC не выбрасываются наружу: любой неуспешный вызов превращается в `GRPCResponse` с соответствующим кодом. Это удобно в автотестах, где неуспешный ответ — такой же ожидаемый результат:

```python
response = client.send_example_request(data)

assert response.status_code == grpc.StatusCode.NOT_FOUND
assert response.details == "заказ не найден"
```

Если же ошибку нужно превратить в исключение, используйте `raise_for_status()`.

Для преобразования ответного сообщения есть метод `with_parser`. Это полезно, когда ответ нужно разобрать в pydantic-модель или достать из него одно свойство:

```python
from pydantic import BaseModel

from grpc_client import GRPCClient, GRPCResponseWithParser, MetadataType

from api import example_pb2, example_pb2_grpc


class ResponseModel(BaseModel):
    prop1: str
    prop2: int
    prop3: bool


class MyCustomClient(GRPCClient[example_pb2_grpc.ExampleStub]):
    @property
    def stub_class(self) -> type[example_pb2_grpc.ExampleStub]:
        return example_pb2_grpc.ExampleStub

    def send_example_request(
        self,
        data: example_pb2.RequestMessage,
        metadata: MetadataType | None = None,
    ) -> GRPCResponseWithParser[example_pb2.ResponseMessage, ResponseModel]:
        """Отправить тестовый gRPC-запрос в сервис.

        :param data: данные запроса
        :param metadata: метаданные запроса (аналог заголовков HTTP)
        :return: объект ответа с методом разбора ответного сообщения
        """
        response = self.send_unary_unary_request(
            msg=data,
            method=self.stub.ExampleMethod,
            metadata=metadata,
        )

        def parser(msg: example_pb2.ResponseMessage) -> ResponseModel:
            return ResponseModel(
                prop1=msg.prop1,
                prop2=msg.prop2,
                prop3=msg.prop3,
            )

        return response.with_parser(parser)
```

Разобранное сообщение возвращает метод `parse()`.

### 6. Потоки

Методы `send_unary_stream_request` и `send_stream_stream_request` возвращают `GRPCStreamResponse` — сообщения читаются лениво, по мере поступления, и не буферизуются.

Если нужны все сообщения сразу, вызовите `collect()`: он дочитает поток и вернёт привычный `GRPCResponse` со списком сообщений и итоговым статусом.

```python
response = client.send_server_stream(data).collect()

assert response.status_code == grpc.StatusCode.OK
for message in response.message():
    ...
```

Ленивое чтение полезно для длинных и бесконечных потоков:

```python
with client.send_server_stream(data) as stream:
    for message in stream:
        if message.is_last:
            break
```

⚠️ Поток удерживает вызов открытым, поэтому его нужно либо дочитать до конца, либо закрыть. Контекстный менеджер отменяет незавершённый вызов на выходе. Можно отменить и явно — методом `cancel()`.

Итоговый статус и trailing-метаданные сервер сообщает только после завершения потока, поэтому до окончания чтения они недоступны — обращение к ним бросит `StreamNotConsumedError`:

```python
stream = client.send_server_stream(data)
messages = list(stream)

stream.status_code  # доступен только теперь
stream.trailing_metadata
```

Чтобы ограничить количество сообщений, передайте `limit` — вызов будет отменён по достижении предела:

```python
response = client.send_server_stream(data).collect(limit=100)
```

ℹ️ Поток читается один раз: повторное чтение бросит `StreamConsumedError`. Если сообщения нужны повторно, сохраните их через `collect()`.

### 7. Параметры вызова

Настройки клиента распространяются на все запросы, а параметры одного вызова задаются через `CallOptions`:

```python
from grpc_client import CallOptions

response = client.send_example_request(
    data,
    options=CallOptions(
        timeout=120,  # своё ограничение времени для долгого метода
        metadata={"x-attempt": "2"},
        wait_for_ready=True,  # подождать готовности канала вместо ошибки UNAVAILABLE
        compression=grpc.Compression.Gzip,
    ),
)
```

`timeout=None` означает вызов без ограничения времени, а незаданный `timeout` берётся из настроек клиента — это разные вещи.

### 8. Метаданные

Метаданные можно передавать словарём либо последовательностью пар — второй вариант нужен, когда у ключа несколько значений:

```python
client.send_example_request(data, metadata={"x-order-id": "A-1024"})
client.send_example_request(data, metadata=[("x-feature", "search"), ("x-feature", "ranking")])
```

Метаданные ответа возвращаются объектом `Metadata`. Он ведёт себя как словарь, но сохраняет порядок и повторяющиеся ключи, а имена ключей сравнивает без учёта регистра:

```python
response.trailing_metadata["x-request-id"]  # первое значение ключа
response.trailing_metadata.get_all("x-feature")  # все значения ключа
response.trailing_metadata.pairs()  # все пары, включая повторяющиеся ключи
```

ℹ️ Двоичные значения допустимы только для ключей с суффиксом `-bin` — это требование gRPC.

### 9. Ошибки и расширенный статус

Сервисы часто передают подробности ошибки в `google.rpc.Status`. Библиотека разбирает их и отдаёт через `error_status`:

```python
response = client.send_example_request(data)

if response.error_status:
    print(response.error_status.code)  # числовой код google.rpc.Code
    print(response.error_status.message)  # текст ошибки
    print(response.error_status.details)  # типизированные подробности

    # подробности можно искать по типу сообщения
    bad_request = response.error_status.of_type(error_details_pb2.BadRequest)
```

Неизвестные библиотеке типы подробностей остаются в виде `google.protobuf.Any`.

Исключения библиотеки наследуются от `GRPCClientError`:

| Исключение | Когда возникает |
| --- | --- |
| `MessageUndefinedError` | обращение к `message()` ответа, в котором сообщения нет |
| `ResponseStatusError` | `raise_for_status()` при статусе, отличном от OK |
| `StreamConsumedError` | повторное чтение уже прочитанного потока |
| `StreamNotConsumedError` | обращение к итоговому статусу недочитанного потока |

### 10. Авторизация

Библиотека не знает, откуда берётся токен, — она описывает контракт `ClientAuth`:

```python
class ClientAuth(Protocol):
    def token(self) -> str: ...
    def refresh(self, rejected_token: str) -> str: ...
```

Отвергнутый токен передаётся в `refresh()`, чтобы реализация могла отличить «токен действительно протух»
от «его уже обновил соседний запрос, пока этот ждал блокировку», и не ходила во внешний сервис лишний раз.

Реализация отвечает за выдачу токена: поход во внешний сервис, кеширование и срок жизни. Подстановку заголовка и повтор запроса берёт на себя клиент:

```python
client = MyCustomClient.from_addr(
    "example.com:443",
    options.with_auth(my_auth),
)
```

Что делает клиент:

- добавляет к каждому запросу заголовок `authorization: Bearer <токен>`;
- если запрос пришёл с ответом `UNAUTHENTICATED`, запрашивает новый токен через `refresh(отвергнутый_токен)` и повторяет унарный запрос;
- не вмешивается, если вызывающий код передал собственный заголовок `authorization`.

⚠️ Повтор выполняется только для унарных запросов: поток запросов после первой отправки уже исчерпан, а у потока ответов итоговый статус известен лишь после вычитывания. Повтор можно отключить: `options.with_auth(my_auth, retry_on_unauthenticated=False)`.

ℹ️ Готовая авторизация в IAM реализована в библиотеке [`cloudru-qa-grpc-client-auth`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client-auth).

### 11. Логирование

```python
import logging

client = MyCustomClient.from_addr(
    "example.com:443",
    options.with_logger(
        logging.getLogger("example"),
        sanitize_keys=["user.password"],
        json_indent=2,
    ),
)
```

Логируются все четыре типа вызовов. Для потоков в лог попадает итоговый статус и количество сообщений — сами сообщения не логируются, потому что их вычитывание ради лога изменило бы поведение вызова.

ℹ️ В асинхронном клиенте считаются сообщения, полученные через `async for` и `collect()` — других способов чтения потока клиент не предоставляет.

Секреты маскируются:

- в метаданных — по имени ключа, без учёта регистра;
- в теле сообщения — двумя способами, в зависимости от того, как задан ключ:
  - имя без разделителей (`password`) маскирует поле с таким именем на любом уровне вложенности, включая элементы списков;
  - путь с точкой, звёздочкой или скобками (`user.password`, `items.*.token`) применяется как [glom-путь](https://glom.readthedocs.io/en/latest/).

Имена полей сравниваются с точностью до стиля записи, поэтому `access_token` скрывает и `accessToken` (protobuf сериализует поля в camelCase), но не затрагивает поле с другими границами слов вроде `sec_ret`.

Типовые ключи (`authorization`, `cookie`, `password`, `token` и другие) маскируются всегда — и в метаданных, и во вложенных полях тела. Отключить это можно параметром `use_default_sanitize_keys=False`.

Общие для всех клиентов настройки логирования задаются через `configure_logging`, значения можно переопределить переменными окружения:

```python
from grpc_client import configure_logging

configure_logging(
    log_level=logging.INFO,
    json_indent=2,
    payload_log_maxlength=4096,
)
```

| Переменная окружения | Что задаёт |
| --- | --- |
| `GRPC_CLIENT_LOG_LEVEL` | уровень логирования успешных запросов |
| `GRPC_CLIENT_ERR_LOG_LEVEL` | уровень логирования запросов с ошибкой |
| `GRPC_CLIENT_JSON_INDENT` | отступ при форматировании JSON |
| `GRPC_CLIENT_USE_LINE_BREAKS` | разносить ли свойства лога по строкам |
| `GRPC_CLIENT_PAYLOAD_LOG_MAXLENGTH` | максимальная длина тела сообщения в логе |

#### Свой формат лога

`with_logger` пишет каждый вызов одной строкой. Если лог нужен в другом виде — например отдельными полями в структурированном логгере — вместо логгера клиенту передаётся приёмник записей:

```python
from grpc_client import LogSink, RequestRecord, ResponseRecord, options


class MySink(LogSink):
    def is_enabled_for(self, level: int) -> bool:
        return True

    def write_request(self, level: int, record: RequestRecord) -> None: ...

    def write_response(self, level: int, record: ResponseRecord) -> None: ...


client = MyCustomClient.from_addr("example.com:443", options.with_log_sink(MySink()))
```

`LogSink` — это `Protocol`, поэтому наследование необязательно, но с ним mypy проверит сигнатуры.

Клиент собирает записи и выбирает уровень: успешный вызов пишется уровнем `log_level`, вызов с ошибкой — `err_log_level`. Приёмник решает только, куда и в каком виде запись попадёт, поэтому маскирование и оформление он настраивает сам — например через `LogFormat.from_config(...)` (импортируется из `grpc_client`), которая подставляет значения `configure_logging`.

Исход вызова читается по полям записи: `record.succeeded` отличает успех от ошибки, `record.is_stream` — завершившийся поток от унарного ответа. Разбирать сочетание `status_code`, `message` и `messages_count` вручную не нужно.

`is_enabled_for` клиент спрашивает перед каждой записью, поэтому он должен быть дешёвым.

Приёмник должен выдерживать вызовы из разных потоков и не работать долго. Если он бросит исключение, клиент его погасит: вызов не сорвётся, но запись потеряется.

Готовая реализация для structlog — в библиотеке [`cloudru-qa-grpc-client-structlog`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client-structlog).

### 12. Асинхронный клиент

`AsyncGRPCClient` повторяет интерфейс синхронного клиента поверх `grpc.aio`:

```python
from grpc_client import AsyncGRPCClient, AsyncGRPCStreamResponse, GRPCResponse, options

from api import example_pb2, example_pb2_grpc


class MyAsyncClient(AsyncGRPCClient[example_pb2_grpc.ExampleStub]):
    @property
    def stub_class(self) -> type[example_pb2_grpc.ExampleStub]:
        return example_pb2_grpc.ExampleStub

    async def send_example_request(
        self,
        data: example_pb2.RequestMessage,
    ) -> GRPCResponse[example_pb2.ResponseMessage]:
        return await self.send_unary_unary_request(data, self.stub.ExampleMethod)


async with MyAsyncClient.from_addr("localhost:9000", options.with_insecure_channel()) as client:
    response = await client.send_example_request(data)
```

Отличия от синхронного клиента:

- методы отправки нужно ожидать через `await`;
- потоки возвращают `AsyncGRPCStreamResponse`, который читается через `async for`, а статус и метаданные отдаёт корутинами: `await stream.status_code()`;
- закрытие — `await client.close()` либо `async with`;
- интерцепторы `grpc.aio` задаются только при создании канала, поэтому `from_channel()` с опциями,
  которые добавляют интерцепторы (`with_auth`, `with_logger`, `with_autogenerated_*`, `with_interceptor`),
  завершится ошибкой: такой канал нужно создавать самому через `grpc.aio.insecure_channel(..., interceptors=[...])`
  либо строить клиент через `from_addr()`;
- авторизация требует асинхронной реализации контракта `AsyncClientAuth`, где `token()` и `refresh()` объявлены корутинами.

Опции у обоих клиентов общие: `options.with_logger(...)` подключит нужный вариант интерцептора сам.

### 13. Свои интерцепторы

**Interceptor** — это перехватчик gRPC-запросов. Их можно использовать, чтобы добавить данные в запрос, собрать метрики, что-то закешировать.

Интерцепторы пишутся на обычном API grpcio. Если задача сводится к добавлению метаданных, удобнее унаследоваться от `MetadataInterceptor` — он покрывает все четыре типа вызовов:

```python
from grpc_client.interceptors import MetadataInterceptor
from grpc_client.types import MetadataItems


class TenantInterceptor(MetadataInterceptor):
    """Добавляет к каждому запросу идентификатор тенанта."""

    def __init__(self, tenant: str):
        self._tenant = tenant

    def metadata_to_add(self, call_details) -> MetadataItems:
        return (("x-tenant", self._tenant),)


client = MyCustomClient.from_addr(
    "localhost:9000",
    options.with_interceptor(TenantInterceptor("warehouse-42")),
)
```

Для асинхронного клиента есть `AsyncMetadataInterceptor` с тем же контрактом, где `metadata_to_add` объявлен корутиной.

⚠️ Определять успех вызова проверкой `isinstance(outcome, grpc.RpcError)` нельзя: объекты потоковых вызовов grpcio реализуют одновременно `grpc.Call` и `grpc.RpcError` даже когда вызов идёт нормально. Ориентируйтесь на код статуса — для этого есть готовая функция `grpc_client.interceptors.base.outcome_code`.

ℹ️ Больше примеров можно найти в [тестах библиотеки](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client/tests/).

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                     # зависимости всех библиотек строго по uv.lock
make test-grpc-client         # тесты этой библиотеки
make typecheck-grpc-client    # mypy для этой библиотеки
make check                    # форматирование, ruff, mypy и тесты всего набора
```

⚠️ **Важно**, чтобы библиотека оставалась легковесной и универсальной. Новые зависимости стоит
добавлять, только если есть уверенность, что они необходимы всем пользователям библиотеки.

Тестам нужен запущенный Docker: контейнер с сервисом [grpcbin](https://grpcb.in/) поднимается
и останавливается автоматически через [lovely-pytest-docker](https://github.com/lovelysystems/lovely-pytest-docker).
`make test-grpc-client` перед запуском заново генерирует тестовые `pb2.py` из `proto/`;
отдельно генерацию запускает `make gen-test-api`.

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-grpc-client PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `grpc-client/v<версия>`. Версия в теге должна совпадать с версией
в `packages/grpc-client/pyproject.toml`, иначе публикация остановится.
