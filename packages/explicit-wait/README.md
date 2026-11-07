# Явные ожидания

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-explicit-wait)](https://pypi.org/project/cloudru-qa-explicit-wait/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-explicit-wait)](https://pypi.org/project/cloudru-qa-explicit-wait/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-explicit-wait)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Функции для явного ожидания событий в автотестах: синхронные и асинхронные, с диагностикой
причины таймаута и без внешних зависимостей.

- [Явные ожидания](#явные-ожидания)
  - [Установка](#установка)
  - [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
  - [Быстрый старт](#быстрый-старт)
  - [Функции ожидания](#функции-ожидания)
  - [Параметры](#параметры)
    - [`timeout_seconds`](#timeout_seconds)
    - [`sleep_seconds`](#sleep_seconds)
    - [`max_attempts`](#max_attempts)
    - [`message`](#message)
    - [`expected_exceptions` и `retry_on_exception`](#expected_exceptions-и-retry_on_exception)
    - [`on_attempt`, `on_timeout` и `on_attempts_exhausted`](#on_attempt-on_timeout-и-on_attempts_exhausted)
    - [`cancel_event`](#cancel_event)
    - [`clock` и `sleeper`](#clock-и-sleeper)
  - [Диагностика таймаута](#диагностика-таймаута)
  - [Иерархия исключений](#иерархия-исключений)
  - [Агрегация предикатов](#агрегация-предикатов)
  - [Асинхронные ожидания](#асинхронные-ожидания)
  - [Декораторы](#декораторы)
  - [Конфигурация](#конфигурация)
  - [Логирование и отчёты](#логирование-и-отчёты)
  - [Расширение](#расширение)
  - [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-explicit-wait
```

Библиотека импортируется как модуль `explicit_wait`.

## Скиллы для AI-агентов

В пакет включён скилл [`explicit-wait-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/explicit-wait-usage/SKILL.md)
с примерами и правилами использования библиотеки для AI-агентов. Установите библиотеку
в окружение своего проекта, затем из его корня выполните (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill explicit-wait-usage --yes
```

Для Claude Code добавьте `--claude`. Инструкции поставляются вместе с версией библиотеки.

## Быстрый старт

```python
from explicit_wait import WaitOptions

from explicit_wait import wait_until


def get_users() -> list[User]:
    """Получаем список пользователей."""
    response = client.send(...)
    return response.model()


# Ждём, пока в списке не появится 2 пользователя
wait_until(
    lambda: len(get_users()) == 2,
    options=WaitOptions(timeout_seconds=30, message="в списке появится 2 пользователя"),
)
```

Все параметры, кроме предиката, передаются только по имени — так вызов нельзя прочитать
неправильно, а таймаут невозможно случайно передать как паузу.

## Функции ожидания

| Функция | Что делает | Что возвращает |
| --- | --- | --- |
| `wait_until` | ждёт, пока предикат не вернёт значение, отличное от falsy | значение предиката |
| `wait_or_none` | то же, но не падает при неудаче | значение предиката или `None` |
| `wait_while` | ждёт, пока предикат не перестанет возвращать truthy | `None` |
| `async_wait_until` | `wait_until` в event loop | значение предиката |
| `async_wait_or_none` | `wait_or_none` в event loop | значение предиката или `None` |
| `async_wait_while` | `wait_while` в event loop | `None` |
| `wait_for` | декоратор: вызывает функцию до первого truthy-результата | значение функции |
| `async_wait_for` | то же для корутинной функции | значение функции |

**Falsy значения** — это значения, которые ведут себя как ложь в логических операциях:
`False`, `0`, `""`, `None`, `[]`, `{}`.

## Параметры

Настройки одного ожидания передаются через `options=WaitOptions(...)`. Объект можно использовать повторно.

### `timeout_seconds`

Максимальное время ожидания в секундах. `None` — взять значение из конфигурации
(по умолчанию 64 секунды). Чтобы ждать бесконечно, нужно указать это явно:

```python
from explicit_wait import WaitOptions

import math

wait_until(predicate, options=WaitOptions(timeout_seconds=math.inf, max_attempts=100))
```

Нуль, отрицательное значение и `NaN` отклоняются с `ValueError`.

### `sleep_seconds`

Пауза между попытками. Задаётся числом, кортежем или объектом `Backoff`:

```python
from explicit_wait import WaitOptions

from explicit_wait import Backoff, wait_until

# Постоянный интервал 1 секунда
wait_until(predicate, options=WaitOptions(sleep_seconds=1))

# Рост с множителем 2 до максимума: 1, 2, 4, 8, 16, 32, 64, 100, 100, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, 100)))

# Рост с заданным множителем: 1, 3, 9, 27, 81, 100, 100, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, 100, 3)))

# Рост без ограничения сверху: 1, 2, 4, 8, 16, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, None)))

# Явная стратегия с джиттером: из каждой паузы случайно вычитается до 20%
wait_until(
    predicate,
    options=WaitOptions(
        sleep_seconds=Backoff(
            initial_seconds=1,
            maximum_seconds=30,
            multiplier=2,
            jitter=0.2,
        ),
    ),
)
```

Джиттер нужен, когда параллельные тесты опрашивают один и тот же сервис: без него их
запросы выстраиваются в синхронные волны.

Значения проверяются при создании стратегии, а не «где-то потом» внутри `time.sleep`:

- начальный интервал — конечное число больше нуля;
- максимум — конечное число не меньше начального интервала либо `None`;
- множитель — конечное число не меньше 1;
- джиттер — число в диапазоне `[0, 1)`;
- кортеж — ровно 2 или 3 элемента, `None` допустим только в позиции максимума.

### `max_attempts`

Ограничение по числу попыток вместо или вместе с ограничением по времени. При исчерпании
попыток выбрасывается `AttemptsExhaustedError`.

```python
from explicit_wait import WaitOptions

wait_until(predicate, options=WaitOptions(max_attempts=5, sleep_seconds=2))

# Снять ограничение, заданное в конфигурации, для одного ожидания
wait_until(predicate, options=WaitOptions(max_attempts=None))
```

Пропущенный аргумент означает «взять значение из конфигурации», явный `None` — «ограничения
по числу попыток нет». То же различие действует в `configure` и `configured`.

Если дедлайн уже наступил, причиной остановки считается время, а не попытки: сначала
проверяется дедлайн, затем лимит попыток, затем возможность вместить следующую паузу.

### `message`

Человекочитаемое описание того, чего ждём. Попадает в текст ошибки, поэтому упавший тест
объясняет себя сам. Без `message` подставляется имя функции-предиката; для лямбды это
малоинформативно, поэтому с лямбдами `message` стоит указывать всегда.

Адрес объекта и `repr` аргументов в сообщение не попадают — в логи не утекут ни бесполезные
адреса, ни чувствительные данные из аргументов `functools.partial`.

### `expected_exceptions` и `retry_on_exception`

`expected_exceptions` — исключения предиката, которые считаются нормальной частью ожидания.
`retry_on_exception` — дополнительный фильтр: повторять попытку или пробросить ошибку наружу.

```python
from explicit_wait import WaitOptions

# Ждём, пока сервис поднимется, игнорируя ошибки соединения
wait_until(predicate, options=WaitOptions(expected_exceptions=(ConnectionError, TimeoutError)))

# Ретраим только 5xx, а 4xx пробрасываем сразу
wait_until(
    predicate,
    options=WaitOptions(
        expected_exceptions=httpx.HTTPStatusError,
        retry_on_exception=lambda error: isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500,
    ),
)
```

Фильтр получает исключение как `Exception`, поэтому обращаться к полям конкретного класса
нужно после `isinstance`: типы `expected_exceptions` и `retry_on_exception` между собой
не связаны.

Исключение, не попавшее в `expected_exceptions`, пробрасывается наружу без изменений вместе
с исходным traceback. `KeyboardInterrupt`, `SystemExit` и `asyncio.CancelledError` не
перехватываются никогда.

Ошибки самой библиотеки (`WaitError` и его наследники) не считаются ожидаемыми ни при каких
`expected_exceptions`. Иначе таймаут вложенного ожидания молча превратился бы в очередную
неудачную попытку внешнего. Если повтор по вложенному ожиданию всё же нужен, преобразуйте
его в falsy-результат внутри предиката:

```python
from explicit_wait import WaitOptions

wait_until(lambda: wait_or_none(inner_condition, options=WaitOptions(timeout_seconds=5)) is not None)
```

### `on_attempt`, `on_timeout` и `on_attempts_exhausted`

Хуки получают объект `Attempt`:

```python
from explicit_wait import WaitOptions

from explicit_wait import Attempt, wait_until


def log_attempt(attempt: Attempt) -> None:
    print(f"попытка {attempt.number}: {attempt.result!r}, прошло {attempt.elapsed_seconds:.1f}s")


wait_until(predicate, options=WaitOptions(on_attempt=log_attempt))
```

| Поле `Attempt` | Значение |
| --- | --- |
| `number` | номер попытки, начиная с 1 |
| `elapsed_seconds` | время с начала ожидания |
| `result` | результат предиката (`None`, если он завершился ожидаемым исключением) |
| `exception` | ожидаемое исключение предиката или `None` |
| `next_sleep_seconds` | пауза перед следующей попыткой или `None`, если она не запланирована |
| `has_no_planned_sleep` | признак того, что на момент решения пауза не запланирована |

`has_no_planned_sleep` — снимок плана, а не гарантия финальности: попытка может оказаться
последней и при запланированной паузе, если ожидание отменят извне, пробуждение случится
позже заказанного или время израсходует сам хук.

`on_attempt` вызывается после каждой попытки, включая попытки с falsy-результатом и попытки
с ожидаемым исключением. Он не вызывается, если предикат выбросил неожидаемое исключение:
такое ожидание прекращается немедленно.

`on_timeout` срабатывает только при остановке по времени, `on_attempts_exhausted` — только
при исчерпании `max_attempts`. При отмене через `cancel_event` не вызывается ни один из них.

Время, потраченное хуками, учитывается в дедлайне: если `on_attempt` израсходовал остаток
бюджета, запланированная пауза не выполняется, а причиной остановки становится наступивший
дедлайн — даже если до хука уже были исчерпаны попытки. Диагностика в исключении и объект
`Attempt`, который получает терминальный хук, снимаются одним чтением часов до вызова хука,
поэтому его собственное время в них не попадает.

Исключение из самого хука пробрасывается наружу и **не** смешивается с исключениями
предиката, даже если его тип указан в `expected_exceptions`.

### `cancel_event`

Позволяет прервать долгое ожидание извне. Когда параметр задан, пауза между попытками
выполняется через `Event.wait`, поэтому параметр `sleeper` не используется.

```python
from explicit_wait import WaitOptions

from threading import Event

cancel = Event()
# из другого потока: cancel.set()

wait_until(predicate, options=WaitOptions(timeout_seconds=600), cancel_event=cancel)
```

При отмене выбрасывается `WaitCancelledError`. `wait_or_none` его не подавляет: отмена —
это не «не дождались».

В асинхронном варианте отдельный параметр не нужен — работает штатная отмена задачи.

### `clock` и `sleeper`

Источник времени и функция сна. Позволяют тестировать код с ожиданиями без реальных пауз.
По умолчанию — `time.monotonic` и `time.sleep` (`asyncio.sleep` в асинхронных функциях).

## Диагностика таймаута

Ошибка остановки несёт всё, что нужно для разбора упавшего теста:

```python
from explicit_wait import WaitOptions

from explicit_wait import TimeoutExpiredError, wait_until

try:
    wait_until(
        lambda: get_order().status == "ready", options=WaitOptions(timeout_seconds=30, message="заказ станет ready")
    )
except TimeoutExpiredError as error:
    print(error.attempts)  # сколько было попыток
    print(error.elapsed_seconds)  # сколько реально прошло
    print(error.last_result)  # что предикат вернул в последний раз
    print(error.last_exception)  # какое ожидаемое исключение было последним
```

Текст ошибки собирается из этих же полей. Чаще всего ожидание останавливается потому, что
следующая пауза уже не помещается до дедлайна — тогда `deadline_reached` равно `False`:

```text
No further attempt could start before the 30 second deadline waiting for заказ станет ready (attempts: 4, elapsed: 14.000s, last result: False)
```

Если дедлайн действительно наступил — например, его израсходовал сам предикат или пробуждение
случилось позже заказанного, — сообщение другое, а `deadline_reached` равно `True`:

```text
Timeout of 30 seconds expired waiting for заказ станет ready (attempts: 3, elapsed: 30.500s, last result: False)
```

Если попытки падали с ожидаемым исключением, оно попадает и в сообщение, и в `__cause__`,
поэтому traceback показывает исходную причину:

```text
No further attempt could start before the 30 second deadline waiting for сервис ответит (attempts: 4, elapsed: 14.002s, last exception: ConnectionError: [Errno 61] Connection refused)
```

Слишком длинный `repr` последнего результата обрезается, чтобы не раздувать отчёт.

## Иерархия исключений

```text
WaitError
├── WaitStoppedError            — дождаться не удалось
│   ├── TimeoutExpiredError     — истекло время (наследуется и от встроенного TimeoutError)
│   └── AttemptsExhaustedError  — исчерпаны попытки max_attempts
├── InvalidPredicateError       — предикат нарушил контракт (наследуется и от TypeError)
└── WaitCancelledError          — ожидание прервано через cancel_event
```

`InvalidPredicateError` наследуется от `TypeError`, поэтому ловится привычным способом, и от
`WaitError`, поэтому его нельзя случайно поглотить через `expected_exceptions`.

Все исключения переживают `pickle`, `copy` и `deepcopy` вместе со своими полями, заметками
`add_note` и состоянием пользовательских наследников. Исключение не сериализуется, если
несериализуем сам `last_result` или `last_exception`.

`TimeoutExpiredError` наследуется от встроенного `TimeoutError`, поэтому таймауты этой
библиотеки и `asyncio` ловятся одним `except TimeoutError`. Таймауты httpx в эту иерархию
не входят — `httpx.TimeoutException` наследуется от `httpx.TransportError`, и его нужно
перехватывать отдельно:

```python
except (TimeoutError, httpx.TimeoutException):
    ...
```

Поле `deadline_reached` у `TimeoutExpiredError` различает две ситуации: дедлайн действительно
наступил либо очередная пауза в него уже не помещалась и начинать попытку было бессмысленно.

## Агрегация предикатов

`AllOf` истинно, когда **все** предикаты истинны одновременно; `AnyOf` — когда истинен хотя
бы один. Предикаты вызываются в порядке перечисления и вычисляются по короткой схеме.

```python
from explicit_wait import WaitOptions

from explicit_wait import AllOf, AnyOf, wait_until

wait_until(
    AnyOf([lambda: get_status() == "ready", lambda: get_status() == "completed"]),
    options=WaitOptions(timeout_seconds=30, message="статус станет ready или completed"),
)

wait_until(
    AllOf([users_loaded, settings_loaded, profile_loaded]),
    options=WaitOptions(timeout_seconds=60, message="все данные загрузятся"),
)
```

Агрегаты не хранят состояние между вызовами: один и тот же объект можно переиспользовать в
нескольких ожиданиях и вызывать из нескольких потоков. Композиция собирается операторами:

```python
ready = AnyOf([status_is("ready"), status_is("completed")]) & AllOf([cache_warm, index_built])
```

Для асинхронных предикатов есть `AsyncAllOf` и `AsyncAnyOf` — они дожидаются каждого предиката
и тоже вычисляются по короткой схеме:

```python
from explicit_wait import WaitOptions

from explicit_wait import AsyncAllOf, async_wait_until

await async_wait_until(
    AsyncAllOf([order_is_paid, invoice_is_issued]),
    options=WaitOptions(timeout_seconds=30, message="заказ оплачен и счёт выставлен"),
)
```

Синхронные `AllOf` и `AnyOf` асинхронные предикаты не принимают и падают с `TypeError`:
корутина — truthy-объект, поэтому незамеченной она превратила бы ложное условие в успешное.

## Асинхронные ожидания

Пауза между попытками выполняется через `asyncio.sleep` и не блокирует event loop, поэтому
фоновые задачи продолжают выполняться между попытками. Предикат может быть как корутинной,
так и обычной функцией — обычная вызывается прямо в event loop, поэтому она сама и все хуки
(`on_attempt`, `on_timeout`, `on_attempts_exhausted`) обязаны быть неблокирующими:
`time.sleep`, файловый ввод-вывод или синхронный HTTP-клиент внутри них остановят весь loop.

Если предикат возвращает awaitable, он всегда ожидается, а не считается конечным значением.

```python
from explicit_wait import WaitOptions

from explicit_wait import async_wait_until


async def order_is_ready() -> bool:
    response = await client.get(f"/orders/{order_id}")
    return response.json()["status"] == "ready"


await async_wait_until(order_is_ready, options=WaitOptions(timeout_seconds=30, message="заказ станет ready"))
```

Отмена работает штатно: `asyncio.CancelledError` не перехватывается, поэтому
`task.cancel()` прерывает ожидание даже при `expected_exceptions=Exception`.

## Декораторы

```python
from explicit_wait import WaitOptions

from explicit_wait import wait_for


@wait_for(options=WaitOptions(timeout_seconds=30, sleep_seconds=1))
def deploy_finished() -> bool:
    return client.get("/deploy").json()["done"]


deploy_finished()  # вернётся, когда деплой завершится
```

Имя декорированной функции подставляется в сообщение об ошибке. Для корутинных функций —
`async_wait_for`.

## Конфигурация

```python
from explicit_wait import configure, configured, get_config, reset_config

# Значения по умолчанию для всех ожиданий в процессе
configure(sleep_seconds=(2, 64), timeout_seconds=64)

# Временное переопределение только внутри блока, снимается в том числе при исключении
with configured(timeout_seconds=5):
    wait_until(predicate)

# Текущие значения и возврат к исходным
get_config()
reset_config()
```

Конфигурация — неизменяемый объект `WaitConfig`, поэтому «полуприменённого» состояния из
несогласованных полей не бывает, а некорректные значения отклоняются сразу при вызове
`configure`. Явно переданный аргумент функции ожидания всегда важнее конфигурации.
Одновременные вызовы `configure` из разных потоков сериализуются блокировкой, поэтому
обновления не теряются.

Области видимости у `configure` и `configured` разные:

| Что | `configure` | `configured` |
| --- | --- | --- |
| Текущий поток | видно | видно |
| Другой поток, `ThreadPoolExecutor` | видно | **не видно** |
| Задача `asyncio`, созданная внутри блока | видно | видно |
| `asyncio.to_thread` | видно | видно |

`configured` хранит переопределение в `contextvars`, поэтому оно наследуется контекстом
корутин, но не обычными потоками. Задача, созданная внутри блока и пережившая выход из него,
продолжит видеть переопределение — контекст фиксируется в момент создания задачи.

В тестах глобальную конфигурацию стоит сбрасывать между тестами, иначе результат начнёт
зависеть от порядка запуска:

```python
import pytest
from explicit_wait import reset_config


@pytest.fixture(autouse=True)
def reset_wait_config():
    reset_config()
    yield
    reset_config()
```

Значения можно собрать из переменных окружения — это удобно, чтобы поднять таймауты на
медленном CI, не меняя код:

```python
from explicit_wait import WaitConfig, configure

config = WaitConfig.from_env()  # префикс по умолчанию EXPLICIT_WAIT_
configure(
    timeout_seconds=config.timeout_seconds,
    sleep_seconds=config.backoff,
    max_attempts=config.max_attempts,
)
```

| Переменная | Формат | Пример |
| --- | --- | --- |
| `EXPLICIT_WAIT_TIMEOUT_SECONDS` | число | `120` |
| `EXPLICIT_WAIT_SLEEP_SECONDS` | число или `начальная,максимальная[,множитель]` | `2,64,2` или `1,none` |
| `EXPLICIT_WAIT_MAX_ATTEMPTS` | целое число | `10` |

## Логирование и отчёты

Библиотека пишет каждую попытку в стандартный логгер на уровне `DEBUG` и не настраивает
обработчики сама:

```python
import logging

logging.getLogger("explicit_wait").setLevel(logging.DEBUG)
```

Шаги для Allure собираются из хука — отдельная зависимость для этого не нужна:

```python
from explicit_wait import WaitOptions

import allure
from explicit_wait import Attempt, wait_until


def report_attempt(attempt: Attempt) -> None:
    with allure.step(f"Попытка {attempt.number}: {attempt.result!r}"):
        pass


wait_until(predicate, options=WaitOptions(on_attempt=report_attempt, message="заказ станет ready"))
```

## Расширение

Корень пакета экспортирует только стабильный API: функции ожидания, агрегаты, `Backoff`,
`Attempt`, конфигурацию, исключения и маркер `UNSET`. Вспомогательные псевдонимы типов и
абстрактные базовые классы доступны из своих модулей и стабильным API не считаются:

```python
from explicit_wait.aggregate import Aggregate, AsyncAggregate
from explicit_wait.backoff import SleepSecondsType
from explicit_wait.types import AsyncPredicate, Clock, ExceptionFilter, ExceptionsType, Predicate, Sleeper
```

Свой агрегат наследуется от `Aggregate` (или `AsyncAggregate`) и реализует `__call__`:

```python
from explicit_wait.aggregate import Aggregate


class MajorityOf(Aggregate):
    """Истинно, когда истинно большинство предикатов."""

    def __call__(self) -> bool:
        passed = sum(1 for predicate in self.predicates if self.check(predicate))
        return passed * 2 > len(self.predicates)
```

Предикаты в своём агрегате нужно вызывать только через `self.check(...)`: он отвергает
асинхронный результат, который иначе молча превратил бы ложное условие в успешное.

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                        # зависимости всех библиотек строго по uv.lock
make test-explicit-wait          # тесты этой библиотеки
make typecheck-explicit-wait     # mypy для этой библиотеки
make check                       # форматирование, ruff, mypy и тесты всего набора
```

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-explicit-wait PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `explicit-wait/v<версия>`. Версия в теге должна совпадать с версией
в `packages/explicit-wait/pyproject.toml`.
