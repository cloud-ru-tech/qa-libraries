# Контекст логирования для автотестов

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-logging-context)](https://pypi.org/project/cloudru-qa-logging-context/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-logging-context)](https://pypi.org/project/cloudru-qa-logging-context/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-logging-context)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Pytest-плагин, который пишет логи каждого теста в отдельный файл и прикрепляет их к
allure-отчёту.

Нужен, чтобы в отчёте по тесту были логи только этого теста. Если писать логи обычным
`FileHandler`, все тесты дописываются в один файл, и прикреплённый к отчёту лог содержит
сообщения других тестов. При параллельном запуске через
[`pytest-xdist`](https://pytest-xdist.readthedocs.io/en/stable/) к этому добавляется
несколько процессов, пишущих в один и тот же файл. Плагин решает и то, и другое.

- [Установка](#установка)
- [Скиллы для AI-агентов](#скиллы-для-ai-агентов)
- [Быстрый старт](#быстрый-старт)
- [Демо-проекты](#демо-проекты)
- [Где искать логи](#где-искать-логи)
- [Настройки](#настройки)
- [Allure](#allure)
- [structlog](#structlog)
- [Другие логгеры и свой формат](#другие-логгеры-и-свой-формат)
- [Разработка](#разработка)

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-logging-context
```

Плагин импортируется как модуль `logging_context`.

## Скиллы для AI-агентов

У этой библиотеки собственного скилла пока нет. Если в проекте установлены другие
библиотеки набора со [скиллами для AI-агентов](https://github.com/cloud-ru-tech/qa-libraries#скиллы-для-ai-агентов),
выбрать и подключить их можно из корня проекта (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

Для Claude Code добавьте `--claude`.

## Быстрый старт

Плагин подключается автоматически при установке, но **ничего не делает**, пока не задан
каталог для логов. Достаточно одной строки:

```toml
# pyproject.toml
[tool.pytest.ini_options]
logging_context_dir = "logs"
```

Свой `conftest.py` нужен только чтобы задать форматтер, который нельзя описать строкой в ini —
например для structlog или JSON (см. ниже). Для такого теста:

```python
import logging

import pytest

logger = logging.getLogger("test-logger")


@pytest.fixture
def user():
    logger.info("создаём пользователя")
    yield {"id": 1}
    logger.info("удаляем пользователя")


def test_login(user):
    logger.info("логинимся под id=%s", user["id"])


@pytest.mark.parametrize("role", ["admin", "guest"])
def test_roles(role):
    logger.info("проверяем роль %s", role)
```

после `pytest` получится:

```
logs/test_login.log
logs/test_roles[48fb048115c186ec].log
logs/test_roles[a81f6f2ab448a918].log
```

```
--- logs/test_login.log
30.07.2026 15:21:40.776 - INFO - Запуск теста id=test_demo.py::test_login
30.07.2026 15:21:40.776 - INFO - создаём пользователя
30.07.2026 15:21:40.778 - INFO - логинимся под id=1
30.07.2026 15:21:40.780 - INFO - удаляем пользователя

--- logs/test_roles[a81f6f2ab448a918].log
30.07.2026 15:21:40.790 - INFO - Запуск теста id=test_demo.py::test_roles[a81f6f2ab448a918] с параметрами {"role": "admin"}
30.07.2026 15:21:40.792 - INFO - проверяем роль admin
```

Логи прикрепляются к allure-отчёту автоматически, если установлен `allure-pytest`.

![allure-report](https://raw.githubusercontent.com/cloud-ru-tech/qa-libraries/master/packages/logging-context/assets/allure-report.png)

## Демо-проекты

В каталоге [`examples/`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/logging-context/examples) лежат два готовых проекта с подключённым плагином. В обоих
один и тот же учебный клиент магазина и одни и те же тесты — с фикстурами, параметризацией,
падающим тестом и повторными попытками. Отличаются они только форматом логов:

| Пример | Что в файлах логов |
|---|---|
| [`examples/logging`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/logging-context/examples/logging) | обычный stdlib `logging`, строки вида `INFO shop.client товар SKU-TEA — Чай листовой` |
| [`examples/structlog`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/logging-context/examples/structlog) | `structlog`, файл в формате JSON Lines |

Команды выполняются из каталога примера, например `packages/logging-context/examples/logging`:

```shell
uv sync
rm -rf logs
uv run pytest -v --clean-alluredir --alluredir=allure-results
npx allure awesome allure-results --single-file --output allure-report
```

Логи каждого теста останутся в `logs/`, отчёт — в `allure-report/index.html`. Для параллельного
прогона через `pytest-xdist` добавьте к pytest `-n 4`. Для сборки отчёта нужен Node.js.

Один тест в обоих примерах падает специально: так в отчёте видно, что к упавшему тесту приложены
именно его логи и по ним сразу понятна причина падения.

## Где искать логи

| Файл | Что в нём |
|---|---|
| `<имя теста>.log` | логи теста, включая setup и teardown всех его фикстур |
| `fixtures_<worker_id>.log` | логи вне тестов — например из `pytest_sessionstart` или при импорте `conftest.py` |

Параметры теста в имени файла заменены их хешом, поэтому имя остаётся коротким и
безопасным при любых значениях параметров. Сами параметры видны в первой строке лога.

Если имя файла повторяется — например при повторном прогоне упавшего теста через
`pytest-rerunfailures` или при одинаковых именах тестовых функций в разных модулях — к
файлу добавляется числовой суффикс. У каждой попытки rerun свой файл, так что в отчёте
видно именно упавшую попытку:

```
logs/test_login.log     <- первая попытка
logs/test_login.2.log   <- вторая
logs/test_login.3.log   <- третья
```

При параллельном запуске к имени добавляется идентификатор воркера — иначе два теста с
одинаковым именем функции, попавшие на разных воркеров, писали бы в один файл:

```
pytest            ->  logs/test_login.log
pytest -n 2       ->  logs/test_login.gw0.log
```

Ни один лог не перезаписывается.

## Настройки

Все настройки задаются в конфигурации pytest (`pyproject.toml`, `pytest.ini`, `tox.ini`).

| Настройка | По умолчанию | Описание |
|---|---|---|
| `logging_context_dir` | — | Каталог для файлов логов. **Пока не задан, плагин не активен.** Относительный путь считается от `rootdir`. |
| `logging_context_launch_id` | — | Подкаталог внутри `logging_context_dir`, например идентификатор запуска CI. Должен быть одним компонентом пути. Переопределяется опцией и переменной окружения, см. ниже. |
| `logging_context_loggers` | root | Логгеры, с которых собирать записи. По умолчанию — root, то есть всё, включая сторонние библиотеки. |
| `logging_context_level` | `INFO` | Минимальный уровень записей. Имя (`DEBUG`) или число. |
| `logging_context_format` | `%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s` | Формат строки лога. |
| `logging_context_date_format` | `%d.%m.%Y %H:%M:%S` | Формат времени. |
| `logging_context_attach_allure` | `true` | Прикреплять файлы логов к allure-отчёту. |
| `logging_context_attach_fixtures_log` | `true` | Прикреплять `fixtures_<worker_id>.log` к каждому тесту. |
| `logging_context_log_test_header` | `true` | Писать в начало файла строку с идентификатором и параметрами теста. |
| `logging_context_params_indent` | `-1` | Отступ при сериализации параметров в JSON. `-1` — в одну строку. |

Пример с сужением до своих логгеров:

```toml
[tool.pytest.ini_options]
logging_context_dir = "logs"
logging_context_loggers = ["test-logger", "api-client"]
logging_context_level = "INFO"
```

По умолчанию в логи попадают и сообщения сторонних библиотек (`httpx`, `urllib3`,
`playwright`) — обычно в отчёте по упавшему тесту это как раз то, что нужно увидеть. Если
такой шум не нужен, перечислите свои логгеры в `logging_context_loggers`.

Одна тонкость: в режиме по умолчанию перехватываются и логгеры с `propagate = False`, даже
если они появились уже после старта прогона. Но если вы задали `logging_context_loggers`,
перечислять такие логгеры нужно явно — сами они найдены не будут.

Параметры теста попадают в заголовок как есть. Если в них бывают токены или пароли,
выключите заголовок: `logging_context_log_test_header = false`.

### Идентификатор запуска

`launch_id` обычно приходит из CI, поэтому его можно передать не только через ini:

```shell
pytest --logging-context-launch-id="$CI_PIPELINE_ID"
```

```shell
LOGGING_CONTEXT_LAUNCH_ID="$CI_PIPELINE_ID" pytest
```

Приоритет: опция командной строки → переменная окружения `LOGGING_CONTEXT_LAUNCH_ID` →
`logging_context_launch_id` из ini. Логи окажутся в `<logging_context_dir>/<launch_id>/`.

## Allure

Ничего настраивать не нужно: если `allure-pytest` установлен и указан `--alluredir`,
плагин сам прикрепляет к каждому тесту его файл логов и файл фикстур. Отключается через
`logging_context_attach_allure = false`, отдельно файл фикстур — через
`logging_context_attach_fixtures_log = false`.

Учтите, что `allure-pytest` **и сам по себе** прикрепляет к каждому тесту вложение `log`.
Если два вложения с логами не нужны, выключите одно из них: `--allure-no-capture` либо
`logging_context_attach_allure = false`.

## structlog

`structlog` нужно направить в stdlib logging, а форматтер задать через хук
`pytest_logging_context_configure`:

```python
# conftest.py
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def pytest_logging_context_configure(handler):
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(ensure_ascii=False),
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
            ],
        ),
    )
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
logging_context_dir = "logs"
logging_context_log_test_header = false
```

`logging_context_log_test_header = false` здесь нужен, чтобы файл остался валидным
JSON Lines.

Хук принимает ещё и `config` — если он нужен, просто добавьте его в сигнатуру. Рабочий пример
целиком лежит в [`examples/structlog`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/logging-context/examples/structlog).

Тест:

```python
import structlog

log = structlog.get_logger("test-logger")


def test_creates_shipment():
    log.info("отправление создано", shipment_id=77)
```

`logs/test_creates_shipment.log`:

```json
{"shipment_id": 77, "event": "отправление создано", "logger": "test-logger", "level": "info"}
```

Bound-контекст сохраняется:

```python
def test_retries_request():
    log = structlog.get_logger("test-logger").bind(request_id="req-51")
    log.warning("странный ответ")
```

```json
{"request_id": "req-51", "event": "странный ответ", "logger": "test-logger", "level": "warning"}
```

Благодаря `foreign_pre_chain` логи сторонних библиотек через обычный `logging` попадают в
тот же файл и в том же формате:

```python
def test_mixes_loggers():
    structlog.get_logger("test-logger").info("из structlog")
    logging.getLogger("legacy.client").warning("из stdlib")
```

`logs/test_mixes_loggers.log`:

```json
{"event": "из structlog", "logger": "test-logger", "level": "info"}
{"event": "из stdlib", "logger": "legacy.client", "level": "warning"}
```

## Другие логгеры и свой формат

Работает любой логгер, который пишет через stdlib `logging`. Для `loguru` понадобится его
штатный `InterceptHandler`, дальше всё так же.

Хук `pytest_logging_context_configure` подходит для любого форматтера, который нельзя
описать строкой в ini:

```python
# conftest.py
import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "time": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def pytest_logging_context_configure(handler):
    handler.setFormatter(JsonFormatter())
```

## Разработка

Библиотека развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                        # зависимости всех библиотек строго по uv.lock
make test-logging-context        # тесты этой библиотеки
make typecheck-logging-context   # mypy для этой библиотеки
make check                       # форматирование, ruff, mypy и тесты всего набора
```

Все проверки должны проходить без ошибок и предупреждений. Тесты прогоняются на Python 3.13 и 3.14.
Окружение для другой версии создаётся отдельно: `make sync test-logging-context PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `logging-context/v<версия>`. Версия в теге должна совпадать с версией
в `packages/logging-context/pyproject.toml`.
