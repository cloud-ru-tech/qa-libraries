# httpx-curlify

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-httpx-curlify)](https://pypi.org/project/cloudru-qa-httpx-curlify/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-httpx-curlify)](https://pypi.org/project/cloudru-qa-httpx-curlify/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-httpx-curlify)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Convert HTTP requests from `httpx.Request` to curl commands. Useful for debugging, logging, and documenting API requests.

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
import httpx
from httpx_curlify import to_curl

request = httpx.Request("GET", "https://example.com/api/users")
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
request = httpx.Request(
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
request = httpx.Request(
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

Mask sensitive data in headers and JSON request bodies using [glom](https://glom.readthedocs.io/en/latest/) syntax:

Mask headers:

```python
request = httpx.Request(
    "GET",
    "https://example.com/api/data",
    headers={
        "Authorization": "Bearer secret_token",
        "X-Api-Key": "api_key_value",
    },
)
curl_command = to_curl(request, sanitize_keys=["authorization", "x-api-key"])
print(curl_command)
```

Output:
```bash
curl -X GET \
  -H 'host: example.com' \
  -H 'authorization: ****' \
  -H 'x-api-key: ****' \
  https://example.com/api/data
```

Mask JSON data:

```python
request = httpx.Request(
    "POST",
    "https://example.com/api/login",
    json={"username": "john", "password": "secret123"},
)
curl_command = to_curl(request, sanitize_keys=["password"])
print(curl_command)
```

Output:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-type: application/json' \
  --json '{"username": "john", "password": "****"}' \
  https://example.com/api/login
```

Mask nested data:

```python
request = httpx.Request(
    "POST",
    "https://example.com/api/data",
    json={"user": {"name": "John", "password": "secret"}},
)
curl_command = to_curl(request, sanitize_keys=["user.password"])
print(curl_command)
```

Output:
```bash
curl -X POST \
  -H 'host: example.com' \
  -H 'content-type: application/json' \
  --json '{"user": {"name": "John", "password": "****"}}' \
  https://example.com/api/data
```

### JSON formatting

Pass additional options to `json.dumps`:

```python
request = httpx.Request(
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
