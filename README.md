# [Cloud.ru](https://cloud.ru) QA libraries

[![Security](https://github.com/cloud-ru-tech/qa-libraries/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/cloud-ru-tech/qa-libraries/actions/workflows/security.yml)
[![Python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/cloud-ru-tech/qa-libraries)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

English | [Русский](README.ru.md)

Python libraries for automated tests. Each library is a separate PyPI package
with its own version and releases.

## Idea

Use a small base client and a set of small libraries that connect to it through options,
instead of one large client that does everything. The base HTTP client only
sends requests. Retries, authorization, structured logs, and Allure steps are separate
packages. Build your own SDK from them: install what you need without pulling in dependencies
for features you do not use.

Options cover the most common testing needs, so you do not need to write your own
wrappers: install a package, import its option, and add it to the client in any project.

```python
import structlog
from http_client import HttpClient, options
from http_client_allure import wrap_requests_in_steps
from http_client_auth import IAM_Auth, IAM_HttpClient
from http_client_retries import with_retries_failed_requests
from http_client_structlog import with_structlogger

auth = IAM_Auth("key_id", "key_secret", IAM_HttpClient("https://iam.example.com"))
client = HttpClient(
    "https://api.example.com",
    options.with_auth(auth),
    with_retries_failed_requests(),
    with_structlogger(structlog.get_logger()),
    wrap_requests_in_steps(),
)
```

An option is a regular function that receives the client during construction and configures it.
You can write your own extension in the same way and use it alongside the built-in options:

```python
from http_client import BaseHttpClient, ClientOption, HttpClient
from http_client_retries import with_retries_failed_requests
from httpx import Request


def with_region(region: str) -> ClientOption:
    def add_region(request: Request) -> None:
        request.headers["X-Region"] = region

    def option(client: BaseHttpClient) -> None:
        client.add_request_hook(add_region)

    return option


client = HttpClient("https://api.example.com", with_region("ru-central-1"), with_retries_failed_requests())
```

The gRPC, SSH, and MCP clients follow the same approach: they also accept `ClientOption` options.

## Libraries

**HTTP**

- [`http-client`](packages/http-client) — base HTTP client built on httpx
- [`http-client-auth`](packages/http-client-auth) — authorization with IAM tokens
- [`http-client-retries`](packages/http-client-retries) — request retries
- [`http-client-responses`](packages/http-client-responses) — typed responses with pydantic models
- [`http-client-structlog`](packages/http-client-structlog) — structured logs with structlog
- [`http-client-allure`](packages/http-client-allure) — requests and responses in Allure reports
- [`httpx-curlify`](packages/httpx-curlify) — httpx requests as curl commands

**gRPC**

- [`grpc-client`](packages/grpc-client) — base gRPC client built on grpcio
- [`grpc-client-auth`](packages/grpc-client-auth) — authorization with IAM tokens
- [`grpc-client-structlog`](packages/grpc-client-structlog) — structured logs with structlog

**Other clients**

- [`ssh-client`](packages/ssh-client) — SSH client
- [`mcp-client`](packages/mcp-client) — client for MCP servers

**Testing tools**

- [`explicit-wait`](packages/explicit-wait) — explicit waits for events
- [`logging-context`](packages/logging-context) — a separate log file for each test
- [`pytest-notifier`](packages/pytest-notifier) — notifications about failed tests
- [`pydantic-extensions`](packages/pydantic-extensions) — pydantic extensions: fields and settings from files

## Installation

Python 3.13 or later is required. Install libraries separately:

```shell
pip install cloudru-qa-http-client
```

Import the module without the prefix: `cloudru-qa-http-client` → `import http_client`.
Each library's README describes its options, examples, and extra dependencies.

## Skills for AI agents

The libraries include skills: instructions and examples that help AI agents use their APIs correctly.

Install the libraries you need in your project environment, then run this from its root:

```shell
uvx library-skills
```

The command finds skills from installed libraries and lets you select the ones you need. It adds them
to the project's `.agents/skills`. For Claude Code, use `uvx library-skills --claude`:
the skills will also be available in `.claude/skills`.

By default, the installer creates symbolic links, so updating a library also updates
the agent instructions. See the [Library Skills documentation](https://library-skills.io/use/) for installer features.
Our skill sources are in [`.agents/skills`](.agents/skills).

## Development

You need [`uv`](https://docs.astral.sh/uv/), GNU Make, and [`checkmake`](https://github.com/checkmake/checkmake). Tests for the gRPC and SSH clients also require Docker. Run all commands from the repository root:

```shell
make sync              # install dependencies for all libraries from uv.lock
make check             # formatting, linters, mypy, and tests for the entire workspace
make test-http-client  # tests for one library
make help              # all available targets
```

Tests run on Python 3.13 and 3.14: `make sync test PYTHON_VERSION=3.14`.

Submit changes through a pull request to `master`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules.

## Releases

Release each library with a git tag named `<name>/v<version>`, for example `http-client/v1.0.0`.
The tag version must match the version in `packages/<name>/pyproject.toml`. After the checks pass,
CI publishes the package to PyPI.

## License

[Apache-2.0](LICENSE)
