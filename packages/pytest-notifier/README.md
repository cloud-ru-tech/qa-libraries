# pytest-notifier

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-pytest-notifier)](https://pypi.org/project/cloudru-qa-pytest-notifier/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-pytest-notifier)](https://pypi.org/project/cloudru-qa-pytest-notifier/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-pytest-notifier)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

Плагин для pytest, который отправляет уведомления об упавших тестах в различные каналы связи (Console, Mattermost, Telegram).

## Особенности

- Отправка уведомлений при падении тестов.
- Поддержка нескольких каналов одновременно.
- Гибкая конфигурация через переменные окружения или `.env` файлы.
- Детальная информация об ошибках, включая traceback.
- Возможность добавлять произвольные сообщения в конец нотификаций (для Telegram и Mattermost).

## Установка

Требуется Python 3.13 или новее.

```shell
pip install cloudru-qa-pytest-notifier
```

Плагин импортируется как модуль `pytest_notifier`.

## Скиллы для AI-агентов

У этой библиотеки собственного скилла пока нет. Если в проекте установлены другие
библиотеки набора со [скиллами для AI-агентов](https://github.com/cloud-ru-tech/qa-libraries#скиллы-для-ai-агентов),
выбрать и подключить их можно из корня проекта (нужен [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

Для Claude Code добавьте `--claude`.

## Использование

Плагин активируется автоматически при запуске `pytest`, если он установлен.

## Конфигурация

Настройка производится через переменные окружения. Префикс для всех переменных: `PYTEST_NOTIFIER_`.

### Основные настройки

`PYTEST_NOTIFIER_DESTINATIONS` - главная переменная, указывающая на то куда отправлять уведомления (битовая маска).

#### Расчет значения DESTINATIONS

Значение формируется суммированием флагов необходимых каналов:

| Канал          | Значение флага |
|----------------|:--------------:|
| **Console**    | `1`            |
| **Mattermost** | `2`            |
| **Telegram**   | `4`            |

**Примеры комбинаций:**

| Комбинация            | Расчет    | Итоговое значение |
|-----------------------|-----------|:-----------------:|
| Только Console        | 1         | `1`               |
| Только Mattermost     | 2         | `2`               |
| Только Telegram       | 4         | `4`               |
| Console + Mattermost  | 1 + 2     | `3`               |
| Console + Telegram    | 1 + 4     | `5`               |
| Mattermost + Telegram | 2 + 4     | `6`               |
| **Все каналы**        | 1 + 2 + 4 | `7`               |

### Mattermost

| Переменная                                      | Описание                                                                   |
|-------------------------------------------------|----------------------------------------------------------------------------|
| `PYTEST_NOTIFIER_MATTERMOST__WEBHOOK_URL`       | URL вебхука для отправки сообщений.                                        |
| `PYTEST_NOTIFIER_MATTERMOST__USERNAME`          | Имя бота.                                                                  |
| `PYTEST_NOTIFIER_MATTERMOST__CHANNEL`           | Канал, куда будут отправляться сообщения                                   |
| `PYTEST_NOTIFIER_MATTERMOST__ICON_EMOJI`        | Emoji для иконки бота (опционально, например `:ghost:`).                   |
| `PYTEST_NOTIFIER_MATTERMOST__TIMEOUT_SECONDS`   | Таймаут запроса в секундах. (По умолчанию: 10 сек.)                        |
| `PYTEST_NOTIFIER_MATTERMOST__SEND_TRACEBACK`    | Отправлять ли traceback ошибки. `true` или `false`. (По умолчанию: `true`) |
| `PYTEST_NOTIFIER_MATTERMOST__ADDITIONAL_MESSAGE`| Дополнительное сообщение, которое будет добавлено в конец нотификации.     |

### Telegram

| Переменная                                    | Описание                                                                   |
|-----------------------------------------------|----------------------------------------------------------------------------|
| `PYTEST_NOTIFIER_TELEGRAM__BOT_TOKEN`         | Токен вашего бота.                                                         |
| `PYTEST_NOTIFIER_TELEGRAM__CHAT_ID`           | ID чата (или канала), куда отправлять сообщения.                           |
| `PYTEST_NOTIFIER_TELEGRAM__TIMEOUT_SECONDS`   | Таймаут запроса в секундах. (По умолчанию: 10.0)                           |
| `PYTEST_NOTIFIER_TELEGRAM__SEND_TRACEBACK`    | Отправлять ли traceback ошибки. `true` или `false`. (По умолчанию: `true`) |
| `PYTEST_NOTIFIER_TELEGRAM__ADDITIONAL_MESSAGE`| Дополнительное сообщение, которое будет добавлено в конец нотификации.     |

### Пример `.env` файла

```ini
# Включить отправку в Mattermost и Telegram (2 + 4 = 6)
PYTEST_NOTIFIER_DESTINATIONS=6

# Mattermost
PYTEST_NOTIFIER_MATTERMOST__WEBHOOK_URL=https://mattermost.example.com/hooks/xxx
PYTEST_NOTIFIER_MATTERMOST__USERNAME=TestBot
PYTEST_NOTIFIER_MATTERMOST__CHANNEL=qa-alerts
PYTEST_NOTIFIER_MATTERMOST__ADDITIONAL_MESSAGE="Документация: https://docs.example.com"

# Telegram
PYTEST_NOTIFIER_TELEGRAM__BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
PYTEST_NOTIFIER_TELEGRAM__CHAT_ID=-1001234567890
PYTEST_NOTIFIER_TELEGRAM__SEND_TRACEBACK=false
PYTEST_NOTIFIER_TELEGRAM__ADDITIONAL_MESSAGE="Свяжитесь с командой QA для подробностей"
```

## Разработка

Плагин развивается в монорепозитории [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries)
вместе с остальными библиотеками `cloudru-qa-*`. Нужны [`uv`](https://docs.astral.sh/uv/), GNU Make
и [`checkmake`](https://github.com/checkmake/checkmake),
команды запускаются из корня репозитория:

```shell
make sync                        # зависимости всех библиотек строго по uv.lock
make test-pytest-notifier        # тесты этого плагина
make typecheck-pytest-notifier   # mypy для этого плагина
make check                       # форматирование, ruff, mypy и тесты всего набора
```

Плагин загружается во всех прогонах тестов монорепозитория, поэтому `make` всегда задаёт
`PYTEST_NOTIFIER_DESTINATIONS=1`: уведомления пишутся только в консоль, даже если в `.env`
настроены Mattermost или Telegram.

Тесты прогоняются на Python 3.13 и 3.14. Окружение для другой версии создаётся отдельно:
`make sync test-pytest-notifier PYTHON_VERSION=3.14`.

Релиз выпускается git-тегом `pytest-notifier/v<версия>`. Версия в теге должна совпадать с версией
в `packages/pytest-notifier/pyproject.toml`.
