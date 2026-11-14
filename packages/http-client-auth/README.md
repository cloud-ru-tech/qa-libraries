# Authorization for the HTTP client

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-auth)](https://pypi.org/project/cloudru-qa-http-client-auth/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-auth)](https://pypi.org/project/cloudru-qa-http-client-auth/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-auth)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

The library adds an IAM access token to outgoing HTTP requests. It obtains the token using a key identifier and secret key, then caches and refreshes it automatically. Calling code does not need to manage token lifetime or retries.

Use it when a service requires `Authorization: Bearer <token>` and IAM issues the token. Works both directly with [httpx](https://www.python-httpx.org/) and with the [HTTP client](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/http-client).

- [Installation](#installation)
- [Skills for AI agents](#skills-for-ai-agents)
- [Quick start](#quick-start)
  - [Synchronous client](#synchronous-client)
  - [Asynchronous client](#asynchronous-client)
  - [OpenID authorization](#openid-authorization)
  - [Closing clients](#closing-clients)
  - [Custom token store](#custom-token-store)
  - [Logging](#logging)
- [Components](#components)
- [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-http-client-auth
```

Import the library as the `http_client_auth` module.

## Skills for AI agents

The package includes the [`http-client-auth-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-auth-usage/SKILL.md) skill
with examples and usage rules for AI agents. Install the library
in your project environment, then run this from its root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-auth-usage --yes
```

For Claude Code, add `--claude`. The instructions are shipped with the library version.

## Quick start

### Synchronous client

```python
import httpx
from http_client import HttpClient, options
from http_client_auth import IAM_Auth, IAM_HttpClient

iam_client = IAM_HttpClient("https://iam.example.com")
auth = IAM_Auth("your_key_id", "your_key_secret", iam_client)

# Directly with httpx
response = httpx.get("https://api.example.com/data", auth=auth)

# With http-client
client = HttpClient("https://api.example.com", options.with_auth(auth))
response = client.get("/data")
```

### Asynchronous client

```python
import httpx
from http_client import AsyncHttpClient, options
from http_client_auth import IAM_AsyncAuth, IAM_AsyncHttpClient

iam_client = IAM_AsyncHttpClient("https://iam.example.com")
auth = IAM_AsyncAuth("your_key_id", "your_key_secret", iam_client)

# Directly with httpx
async with httpx.AsyncClient(auth=auth) as client:
    response = await client.get("https://api.example.com/data")

# With http-client
client = AsyncHttpClient("https://api.example.com", options.with_auth(auth))
response = await client.get("/data")
```

### OpenID authorization

Use a different IAM client; everything else stays the same:

```python
from http_client_auth import IAM_Auth, IAM_OpenID_HttpClient

iam_client = IAM_OpenID_HttpClient("https://iam.example.com")
auth = IAM_Auth("your_key_id", "your_key_secret", iam_client)
```

### Closing clients

The IAM client owns its connection pool and must be closed by the caller; `IAM_Auth` does not own it:

```python
with IAM_HttpClient("https://iam.example.com") as iam_client:
    auth = IAM_Auth("your_key_id", "your_key_secret", iam_client)
    with HttpClient("https://api.example.com", options.with_auth(auth)) as client:
        response = client.get("/data")
```

For a long-lived client, call `close()`; for an asynchronous client, use `await aclose()`.

### Custom token store

By default, tokens are stored in process memory. To reuse them across processes, implement `AuthStore`:

```python
import json
from datetime import datetime

from http_client_auth import AuthStore, IAM_Auth, IAM_HttpClient, Token


class RedisAuthStore(AuthStore):
    def __init__(self, redis_client):
        self._redis = redis_client

    def get(self, key: str) -> Token | None:
        raw = self._redis.get(f"token_for:{key}")
        if raw is None:
            return None
        data = json.loads(raw)
        return Token(data["access_token"], datetime.fromisoformat(data["expires_at"]))

    def set(self, key: str, token: Token) -> None:
        self._redis.set(
            f"token_for:{key}",
            json.dumps(
                {
                    "access_token": token.access_token,
                    "expires_at": token.expires_at.isoformat(),
                }
            ),
        )


iam_client = IAM_HttpClient("https://iam.example.com")
auth = IAM_Auth("your_key_id", "your_key_secret", iam_client, store=RedisAuthStore(redis_client))
```

`IAM_AsyncAuth` accepts `AsyncAuthStore`, the same interface with asynchronous `get` and `set`:

```python
from http_client_auth import AsyncAuthStore, Token


class RedisAsyncAuthStore(AsyncAuthStore):
    def __init__(self, redis_client):
        self._redis = redis_client

    async def get(self, key: str) -> Token | None: ...

    async def set(self, key: str, token: Token) -> None: ...
```

### Logging

If you add logging to the IAM client, pass `IAM_SANITIZE_KEYS`. Otherwise the OpenID request's secret key and the response JWT appear in full in logs: http-client's default masking list does not cover them.

```python
import logging

from http_client import options
from http_client_auth import IAM_SANITIZE_KEYS, IAM_OpenID_HttpClient

iam_client = IAM_OpenID_HttpClient(
    "https://iam.example.com",
    options.with_logger(logging.getLogger("iam"), sanitize_keys=IAM_SANITIZE_KEYS),
)
```

## Components

Authorization:

| Class | Purpose |
|---|---|
| `IAM_Auth` | authorization for synchronous requests; implements `httpx.Auth` |
| `IAM_AsyncAuth` | the same for asynchronous requests |

IAM clients are passed to the authorization object as the first argument after the keys:

| Class | Purpose |
|---|---|
| `IAM_HttpClient` | public IAM API |
| `IAM_AsyncHttpClient` | public IAM API, asynchronous |
| `IAM_OpenID_HttpClient` | API OpenID |
| `IAM_OpenID_AsyncHttpClient` | OpenID API, asynchronous |

Token stores:

| Class | Purpose |
|---|---|
| `AuthStore` | synchronous store interface |
| `AsyncAuthStore` | asynchronous store interface |
| `InMemoryAuthStore` | in-memory store, default for `IAM_Auth` |
| `InMemoryAsyncAuthStore` | in-memory store, default for `IAM_AsyncAuth` |
| `Token` | access token and its expiry time |

Other:

| Name | Purpose |
|---|---|
| `AuthData` | IAM response: access token, lifetime, `id_token` |
| `IAM_SANITIZE_KEYS` | IAM secret keys for `options.with_logger(sanitize_keys=...)` |

Exceptions:

| Class | Raised when |
|---|---|
| `IAM_Error` | base class for all authorization errors |
| `IAM_AuthError` | IAM service returned an unsuccessful status code |
| `IAM_InvalidJsonResponseError` | IAM response could not be parsed |

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                         # install dependencies for all libraries from uv.lock
make test-http-client-auth        # tests for this library
make typecheck-http-client-auth   # mypy for this library
make check                        # formatting, ruff, mypy, and tests for the entire workspace
```

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-http-client-auth PYTHON_VERSION=3.14`.

Publish a release with the git tag `http-client-auth/v<version>`. The tag version must match
the version in `packages/http-client-auth/pyproject.toml`.
