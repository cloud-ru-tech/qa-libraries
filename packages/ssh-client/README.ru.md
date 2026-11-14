# SSH-клиент

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-ssh-client)](https://pypi.org/project/cloudru-qa-ssh-client/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-ssh-client)](https://pypi.org/project/cloudru-qa-ssh-client/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-ssh-client)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

[English](README.md) | Русский

Простая библиотека SSH-клиента для автотестов: синхронный и асинхронный клиенты с опциями
конструктора, декораторами команд и логированием.

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-ssh-client
```

Для структурированного логирования через structlog поставьте библиотеку с дополнением `structlog`:

```shell
pip install "cloudru-qa-ssh-client[structlog]"
```

Библиотека импортируется как модуль `ssh_client`.

## Скиллы для AI-агентов

У этой библиотеки собственного скилла пока нет. Если в проекте установлены другие
библиотеки набора со [скиллами для AI-агентов](../../README.ru.md#скиллы-для-ai-агентов),
выбрать и подключить их можно из корня проекта (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

Для Claude Code добавьте `--claude`.

## Основные возможности

1. Подключение к удаленному хосту по паролю и по ключу
2. Выполнение команд в виде строки или списка фрагментов shell-команды
3. Настройка таймаута для клиента и для отдельных запросов
4. Проверка кода завершения через `raise_for_status=True` для отдельных команд
5. Настройка количества повторных попыток и интервала между ними
6. Повторные попытки при ошибках подключения и при ошибках выполнения команд
7. Результаты в виде объекта с полями stdout, stderr и exit code
8. Логирование запросов и ответов с использованием переданного логгера
9. Маскирование текста в логах запросов/ответов по строкам/регулярным выражениям
10. Асинхронная поддержка через asyncssh
11. Получение данных в реальном времени для интерактивных команд
12. Прерывание выполнения команд по условию с помощью callback-функций

## Пример использования

### Синхронный клиент

```python
import logging
from ssh_client import SyncSSHClient, options

# Создаем логгер
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем клиент
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_request_timeout(30),
    options.with_logger(logger),
)

# Выполняем команду
result = client.execute(["ls", "-la"])
print(f"Exit code: {result.exit_code}")
print(f"Stdout: {result.stdout}")
print(f"Stderr: {result.stderr}")

# Закрываем соединение
client.close()
```

### Асинхронный клиент

```python
import asyncio
import logging
from ssh_client import AsyncSSHClient, options


async def main():
    # Создаем логгер
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Создаем клиент
    client = AsyncSSHClient(
        "example.com",
        22,
        options.with_private_key("user", "/path/to/private/key"),
        options.with_request_timeout(30),
        options.with_logger(logger),
    )

    # Выполняем команду
    result = await client.execute(["ls", "-la"])
    print(f"Exit code: {result.exit_code}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")

    # Закрываем соединение
    await client.aclose()


# Запускаем асинхронную функцию
asyncio.run(main())
```

## Конфигурирование

Для конфигурирования клиента используются опции `ClientOption`. Готовые опции находятся в модуле `options`.

По умолчанию оба клиента проверяют ключ сервера по стандартному `~/.ssh/known_hosts`.
Неизвестный или изменившийся ключ отклоняется. Для отдельного файла используйте
`options.with_known_hosts("/path/to/known_hosts")`; этот файл должен содержать заранее проверенный ключ сервера.

### Доступные опции:

* `with_request_timeout` - настраивает таймаут для запросов SSH-клиента
* `with_connection_timeout` - настраивает таймаут для подключения SSH-клиента
* `with_password` - настраивает имя пользователя и пароль для аутентификации
* `with_private_key` - настраивает имя пользователя и путь к приватному ключу для аутентификации
* `with_known_hosts` - выбирает файл доверенных ключей сервера
* `with_logger` - устанавливает логгер для логирования SSH-запросов и ответов
* `with_structlogger` - устанавливает структурированный логгер для логирования SSH-запросов и ответов (требуется установка с опцией structlog)
* `retry_if_connection_fails` - устанавливает повторы на подключения, которые завершились ошибкой
* `retry_if_command_fails` - устанавливает повторы на команды, которые завершились ошибкой
* `with_connect_decorators` - добавляет пользовательские декораторы для метода подключения
* `with_execute_decorators` - добавляет пользовательские декораторы для метода выполнения команд
* `with_live_execute_callback` - добавляет callback-функции для обработки строк stdout и stderr в реальном времени при выполнении команд

### Пример использования with_live_execute_callback

```python
import logging
from ssh_client import SyncSSHClient, options


# Определяем callback-функции для обработки вывода в реальном времени
def stdout_callback(line):
    print(f"STDOUT: {line}")


def stderr_callback(line):
    print(f"STDERR: {line}")


# Создаем клиент с callback-функциями
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_live_execute_callback(stdout_callback, stderr_callback),
)

# Выполняем команду с живым выводом
result = client.execute_live(["ping", "-c", "3", "google.com"])

# Все строки будут напечатаны в реальном времени через callback-функции
print(f"Exit code: {result.exit_code}")

# Закрываем соединение
client.close()
```

### Прерывание выполнения команд с помощью callback-функций

Функционал прерывания позволяет остановить выполнение команды при достижении определенного условия. Это особенно полезно для длительных команд, когда вы хотите остановить их при появлении определенного текста в выводе.

#### Пример прерывания по stdout (синхронный клиент)

```python
import logging
from ssh_client import SyncSSHClient, options


# Определяем callback-функцию для прерывания по условию
def interrupt_on_keyword(line):
    """Прерываем выполнение, если в строке содержится слово 'ERROR'"""
    print(f"Processing line: {line}")
    return "ERROR" in line


# Создаем клиент
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
)

try:
    # Выполняем команду с прерыванием по условию
    result = client.execute_live(
        ["tail", "-f", "/var/log/application.log"], interrupt_stdout_callback=interrupt_on_keyword
    )

    print(f"Command was interrupted with exit code: {result.exit_code}")
    print("Captured output:")
    for line in result.stdout_lines:
        print(f"  {line}")
finally:
    client.close()
```

#### Пример прерывания по stderr (асинхронный клиент)

```python
import asyncio
from ssh_client import AsyncSSHClient, options


async def main():
    # Определяем callback-функцию для прерывания по stderr
    def interrupt_on_error(line):
        """Прерываем выполнение, если в stderr появляется критическая ошибка"""
        print(f"Error detected: {line}")
        return "CRITICAL" in line or "FATAL" in line

    # Создаем клиент
    client = AsyncSSHClient(
        "example.com",
        22,
        options.with_private_key("user", "/path/to/private/key"),
    )

    try:
        # Выполняем команду с прерыванием по stderr
        result = await client.execute_live(["some-long-running-command"], interrupt_stderr_callback=interrupt_on_error)

        print(f"Command was interrupted with exit code: {result.exit_code}")
        print("Captured stderr:")
        for line in result.stderr_lines:
            print(f"  {line}")
    finally:
        await client.aclose()


# Запускаем асинхронную функцию
asyncio.run(main())
```

В синхронном `execute_live` stdout и stderr объединены через терминал; отдельные stderr callbacks доступны асинхронному клиенту.

При срабатывании interrupt callback-функции команда будет прервана, и метод `execute_live` вернет результат с отрицательным кодом выхода (-1 для синхронного клиента, -2 для асинхронного клиента), содержащий все строки, полученные до момента прерывания.

## Расширенные возможности

### Временные опции с with_options

Метод `with_options` позволяет создавать временные клиенты с дополнительными опциями для однократного выполнения команд:

```python
import logging
from ssh_client import SyncSSHClient, options

# Создаем базовый клиент
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_request_timeout(30),
    options.with_logger(logging.getLogger(__name__)),
)

# Используем with_options для выполнения команды с особыми параметрами
result = client.with_options(
    options.with_request_timeout(60),  # Увеличенный таймаут только для этой команды
    options.retry_if_command_fails(
        retries_attempts_number=3, retries_interval_in_seconds=1
    ),  # Повторные попытки только для этой команды
).execute(["sleep", "10", "&&", "echo", "Done"])

# Базовый клиент остается без изменений
client.close()
```

### Структурированное логирование

Для использования структурированного логирования необходимо установить библиотеку `structlog`:

```shell
pip install "cloudru-qa-ssh-client[structlog]"
```

Пример использования структурированного логирования:

```python
import structlog
from ssh_client import SyncSSHClient, options

# Настройка structlog
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

# Создаем клиент с структурированным логгером
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_structlogger(structlog.get_logger()),
)

# Выполняем команду с структурированным логированием
result = client.execute(["ls", "-la"])
print(f"Exit code: {result.exit_code}")

# Закрываем соединение
client.close()
```

### Механизмы повторных попыток

Клиент поддерживает настройку повторных попыток как для подключения, так и для выполнения команд:

```python
from ssh_client import SyncSSHClient, options

client = SyncSSHClient(
    "unstable-server.com",
    22,
    options.with_password("user", "password"),
    # Повторные попытки подключения
    options.retry_if_connection_fails(
        retries_attempts_number=5, retries_interval_in_seconds=10.0, reraise_exception=True
    ),
    # Повторные попытки выполнения команд
    options.retry_if_command_fails(retries_attempts_number=3, retries_interval_in_seconds=5.0, reraise_exception=True),
)

# Выполняем команду с повторными попытками
result = client.execute(["some-unstable-command"])

# Закрываем соединение
client.close()
```

### Маскирование данных в логах

Для защиты конфиденциальных данных в логах можно использовать маскирование:

```python
import logging
import re
from ssh_client import SyncSSHClient, options

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    # Маскируем конфиденциальные данные в логах
    options.with_logger(
        logger,
        mask_patterns=[
            "password",  # Простая строка для замены
            "secret",  # Еще одна строка для замены
            re.compile(r"token=\w+"),  # Регулярное выражение
        ],
    ),
)

# Выполняем команду с конфиденциальными данными
# В логах эти данные будут замаскированы
result = client.execute(["echo", "password=secret123", "token=abc123def456"])

# Закрываем соединение
client.close()
```

### Пользовательские декораторы

Можно добавлять пользовательские декораторы для методов подключения и выполнения команд:

```python
import time
from functools import wraps
from ssh_client import SyncSSHClient, options


# Пример декоратора для измерения времени выполнения
def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"{func.__name__} took {end_time - start_time:.2f} seconds")
        return result

    return wrapper


# Пример декоратора для обработки ошибок
def error_handler_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error in {func.__name__}: {e}")
            # Можно повторить попытку или выполнить другие действия
            raise

    return wrapper


client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    # Добавляем декораторы для подключения
    options.with_connect_decorators(timing_decorator, error_handler_decorator),
    # Добавляем декораторы для выполнения команд
    options.with_execute_decorators(timing_decorator),
)

# Выполняем команду с декораторами
result = client.execute(["ls", "-la"])

# Закрываем соединение
client.close()
```

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                   # зависимости всех библиотек строго по uv.lock
make test-ssh-client        # тесты этой библиотеки
make typecheck-ssh-client   # mypy для этой библиотеки
make check                  # форматирование, ruff, mypy и тесты всего набора
```

Тестам нужен запущенный Docker: SSH-сервер поднимается в контейнере автоматически. Ключи сервера
и клиента генерируются на каждый прогон и в репозитории не хранятся.

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-ssh-client PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `ssh-client/v<версия>`. Версия в теге должна совпадать с версией
в `packages/ssh-client/pyproject.toml`.

## Лицензия

[Apache-2.0](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)
