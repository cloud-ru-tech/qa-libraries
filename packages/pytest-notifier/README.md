# pytest-notifier

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-pytest-notifier)](https://pypi.org/project/cloudru-qa-pytest-notifier/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-pytest-notifier)](https://pypi.org/project/cloudru-qa-pytest-notifier/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-pytest-notifier)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

A pytest plugin that sends notifications about failed tests to different channels (Console, Mattermost, Telegram).

## Features

- Notifications when tests fail.
- Support for multiple channels at once.
- Flexible configuration through environment variables or `.env` files.
- Detailed error information, including tracebacks.
- Custom messages appended to notifications (for Telegram and Mattermost).

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-pytest-notifier
```

Import the plugin as the `pytest_notifier` module.

## Skills for AI agents

This library does not have its own skill yet. If your project has other
libraries from this collection with [skills for AI agents](https://github.com/cloud-ru-tech/qa-libraries#skills-for-ai-agents),
select and install them from the project root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

For Claude Code, add `--claude`.

## Usage

The plugin activates automatically when running `pytest` if installed.

## Configuration

Configure it through environment variables. All variables use the `PYTEST_NOTIFIER_` prefix.

### Main settings

`PYTEST_NOTIFIER_DESTINATIONS` is the main variable specifying notification destinations (a bitmask).

#### Calculating DESTINATIONS

Add the flags for the required channels:

| Channel | Flag value |
|----------------|:--------------:|
| **Console**    | `1`            |
| **Mattermost** | `2`            |
| **Telegram**   | `4`            |

**Example combinations:**

| Combination | Calculation | Result |
|-----------------------|-----------|:-----------------:|
| Console only | 1 | `1` |
| Mattermost only | 2 | `2` |
| Telegram only | 4 | `4` |
| Console + Mattermost  | 1 + 2     | `3`               |
| Console + Telegram    | 1 + 4     | `5`               |
| Mattermost + Telegram | 2 + 4     | `6`               |
| **All channels** | 1 + 2 + 4 | `7` |

### Mattermost

| Variable | Description |
|-------------------------------------------------|----------------------------------------------------------------------------|
| `PYTEST_NOTIFIER_MATTERMOST__WEBHOOK_URL` | Webhook URL for sending messages. |
| `PYTEST_NOTIFIER_MATTERMOST__USERNAME` | Bot name. |
| `PYTEST_NOTIFIER_MATTERMOST__CHANNEL` | Channel to send messages to. |
| `PYTEST_NOTIFIER_MATTERMOST__ICON_EMOJI` | Bot icon emoji (optional, for example `:ghost:`). |
| `PYTEST_NOTIFIER_MATTERMOST__TIMEOUT_SECONDS` | Request timeout in seconds. Default: 10 seconds. |
| `PYTEST_NOTIFIER_MATTERMOST__SEND_TRACEBACK` | Whether to send the error traceback: `true` or `false`. Default: `true`. |
| `PYTEST_NOTIFIER_MATTERMOST__ADDITIONAL_MESSAGE` | Extra message appended to the notification. |

### Telegram

| Variable | Description |
|-----------------------------------------------|----------------------------------------------------------------------------|
| `PYTEST_NOTIFIER_TELEGRAM__BOT_TOKEN` | Your bot's token. |
| `PYTEST_NOTIFIER_TELEGRAM__CHAT_ID` | Chat or channel ID to send messages to. |
| `PYTEST_NOTIFIER_TELEGRAM__TIMEOUT_SECONDS` | Request timeout in seconds. Default: 10.0. |
| `PYTEST_NOTIFIER_TELEGRAM__SEND_TRACEBACK` | Whether to send the error traceback: `true` or `false`. Default: `true`. |
| `PYTEST_NOTIFIER_TELEGRAM__ADDITIONAL_MESSAGE` | Extra message appended to the notification. |

### Example `.env` file

```ini
# Enable Mattermost and Telegram (2 + 4 = 6)
PYTEST_NOTIFIER_DESTINATIONS=6

# Mattermost
PYTEST_NOTIFIER_MATTERMOST__WEBHOOK_URL=https://mattermost.example.com/hooks/xxx
PYTEST_NOTIFIER_MATTERMOST__USERNAME=TestBot
PYTEST_NOTIFIER_MATTERMOST__CHANNEL=qa-alerts
PYTEST_NOTIFIER_MATTERMOST__ADDITIONAL_MESSAGE="Documentation: https://docs.example.com"

# Telegram
PYTEST_NOTIFIER_TELEGRAM__BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
PYTEST_NOTIFIER_TELEGRAM__CHAT_ID=-1001234567890
PYTEST_NOTIFIER_TELEGRAM__SEND_TRACEBACK=false
PYTEST_NOTIFIER_TELEGRAM__ADDITIONAL_MESSAGE="Contact the QA team for details"
```

## Development

The plugin is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                        # install dependencies for all libraries from uv.lock
make test-pytest-notifier        # tests for this plugin
make typecheck-pytest-notifier   # mypy for this plugin
make check                       # formatting, ruff, mypy, and tests for the entire workspace
```

The plugin loads in every monorepo test run, so `make` always sets
`PYTEST_NOTIFIER_DESTINATIONS=1`: notifications go only to the console, even if `.env`
configures Mattermost or Telegram.

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-pytest-notifier PYTHON_VERSION=3.14`.

Publish a release with the git tag `pytest-notifier/v<version>`. The tag version must match the version
in `packages/pytest-notifier/pyproject.toml`.
