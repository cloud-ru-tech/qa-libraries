# httpx-curlify

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-httpx-curlify)](https://pypi.org/project/cloudru-qa-httpx-curlify/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-httpx-curlify)](https://pypi.org/project/cloudru-qa-httpx-curlify/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-httpx-curlify)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Convert HTTP requests from `httpx2.Request` to curl commands. Useful for debugging, logging, and documenting API requests.

- [httpx-curlify](#httpx-curlify)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Usage](#usage)
    - [Basic usage](#basic-usage)
    - [Masking sensitive data](#masking-sensitive-data)
    - [JSON formatting](#json-formatting)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-httpx-curlify
```

Import the library as the module `httpx_curlify`.

## Skills for AI agents

This library does not have its own skill yet. If your project uses other
libraries from this suite with [skills for AI agents](https://github.com/cloud-ru-tech/qa-libraries#skills-for-ai-agents),
select and enable them from your project root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

For Claude Code, add `--claude`.

## Usage

### Basic usage

Convert a GET request:

```python
import httpx2
from httpx_curlify import to_curl

request = httpx2.Request("GET", "https://example.com/api/users")
curl_command = to_curl(request)
print(curl_command)
```

Output:
```bash
curl -X GET \
  -H 'host: example.com' \
  https://example.com/api/users
```

A POST request with JSON:

```python
request = httpx2.Request(
    "POST",
    "https://example.com/api/users",
    json={"name": "John", "age": 30},
)
curl_command = to_curl(request)
print(curl_command)
```

Output:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-length: 24' \
  -H 'content-type: application/json' \
  --json '{"name": "John", "age": 30}' \
  https://example.com/api/users
```

A request with headers:

```python
request = httpx2.Request(
    "GET",
    "https://example.com/api/data",
    headers={
        "Authorization": "Bearer token123",
        "X-Custom-Header": "custom-value",
    },
)
curl_command = to_curl(request)
print(curl_command)
```

### Masking sensitive data

By default, `to_curl(request)` replaces credential values with `****` in headers and JSON objects at every depth,
including objects inside arrays. It masks common names such as `Authorization`, `Cookie`, `X-Api-Key`, `password`,
`client_secret`, `access_token` and `id_token` without regard to case. URLs and non-JSON bodies are printed as supplied.

```python
request = httpx2.Request(
    "POST",
    "https://example.com/login",
    headers={"Authorization": "Bearer example-token"},
    json={"user": {"password": "example-password"}},
)
command = to_curl(request)  # authorization: ****, "password": "****"
```

For a private replay with the original credentials, pass `sanitize_keys=()`.
A nonempty list replaces the defaults with your own [glom paths](https://glom.readthedocs.io/en/latest/).

```python
command = to_curl(request, sanitize_keys=["authorization", "user.password"])
```

### JSON formatting

Pass additional options to `json.dumps`:

```python
request = httpx2.Request(
    "POST",
    "https://example.com/api/data",
    json={"name": "John", "age": 30},
)
curl_command = to_curl(request, json_dumps_kwargs={"indent": 2})
print(curl_command)
```

Output:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-type: application/json' \
  --json '{
    "name": "John",
    "age": 30
  }' \
  https://example.com/api/data
```

## Development

This library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make
and [`checkmake`](https://github.com/checkmake/checkmake);
run the commands from the repository root:

```shell
make sync                      # dependencies for all libraries from uv.lock
make test-httpx-curlify        # tests for this library
make typecheck-httpx-curlify   # mypy for this library
make lint-fix                  # safe Ruff fixes
make check                     # formatting, Ruff, mypy, and tests for the whole suite
```

Update snapshots with:

```shell
make test-httpx-curlify PYTEST_ARGS=--snapshot-update
```

Tests run on Python 3.13 and 3.14. Each version uses a separate environment:
`make sync test-httpx-curlify PYTHON_VERSION=3.14`.

Create a release with the Git tag `httpx-curlify/v<version>`. The tag version must match the version
in `packages/httpx-curlify/pyproject.toml`.
