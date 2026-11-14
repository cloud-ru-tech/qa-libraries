# Authorization for the gRPC client

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-grpc-client-auth)](https://pypi.org/project/cloudru-qa-grpc-client-auth/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-grpc-client-auth)](https://pypi.org/project/cloudru-qa-grpc-client-auth/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-grpc-client-auth)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Issue and refresh IAM access tokens for the [gRPC client](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client).

- [Authorization for the gRPC client](#authorization-for-the-grpc-client)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Usage](#usage)
    - [Synchronous client](#synchronous-client)
    - [Asynchronous client](#asynchronous-client)
    - [What the library does](#what-the-library-does)
    - [Token store](#token-store)
    - [Masking secrets in logs](#masking-secrets-in-logs)
    - [Components](#components)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-grpc-client-auth
```

Import the library as the `grpc_client_auth` module.

## Skills for AI agents

This library does not have its own skill yet. If your project has other
libraries from this collection with [skills for AI agents](https://github.com/cloud-ru-tech/qa-libraries#skills-for-ai-agents),
select and install them from the project root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

For Claude Code, add `--claude`.

## Usage

### Synchronous client

```python
from grpc_client import options
from grpc_client_auth import IAM_GrpcAuth, IAM_HttpClient

iam_client = IAM_HttpClient("https://iam.example.com")
client = MyGrpcClient.from_addr(
    "service.example.com:443",
    options.with_auth(IAM_GrpcAuth("my_key_id", "my_key_secret", iam_client)),
)

response = client.send_example_request(...)

client.close()
iam_client.close()
```

`IAM_GrpcAuth` implements `grpc_client.ClientAuth`, so connect it with the standard `options.with_auth` option.

### Asynchronous client

```python
from grpc_client import options
from grpc_client_auth import IAM_AsyncHttpClient, IAM_GrpcAsyncAuth

iam_client = IAM_AsyncHttpClient("https://iam.example.com")
client = MyAsyncGrpcClient.from_addr(
    "service.example.com:443",
    options.with_auth(IAM_GrpcAsyncAuth("my_key_id", "my_key_secret", iam_client)),
)

response = await client.send_example_request(...)

await client.close()
await iam_client.aclose()
```

### What the library does

- obtains an IAM token and stores it until expiry;
- issues a new token when it expires or the service returns `UNAUTHENTICATED`;
- avoids another IAM call if a concurrent request has already refreshed the token.

The gRPC client itself adds the `authorization` header and retries the request; see "Authorization" in its README.

Create one authorization object per set of credentials and reuse it across clients: IAM call deduplication works within one object.

Two IAM APIs are available for authorization:

| Client | Route |
| --- | --- |
| `IAM_HttpClient`, `IAM_AsyncHttpClient` | `POST /api/v1/auth/token` |
| `IAM_OpenID_HttpClient`, `IAM_OpenID_AsyncHttpClient` | `POST /auth/system/openid/token` |

### Token store

By default, tokens are stored in process memory. To share them across processes, implement `AuthStore` (or `AsyncAuthStore` for asynchronous usage):

```python
from datetime import datetime

from grpc_client_auth import AuthStore, Token


class RedisAuthStore(AuthStore):
    """Redis token store."""

    def __init__(self, redis_client):
        self._redis = redis_client

    def get(self, key: str) -> Token | None:
        raw = self._redis.hgetall(f"token:{key}")
        if not raw:
            return None
        return Token(raw["access_token"], datetime.fromisoformat(raw["expires_at"]))

    def set(self, key: str, token: Token) -> None:
        self._redis.hset(
            f"token:{key}",
            mapping={
                "access_token": token.access_token,
                "expires_at": token.expires_at.isoformat(),
            },
        )


auth = IAM_GrpcAuth("my_key_id", "my_key_secret", iam_client, store=RedisAuthStore(...))
```

`Token` stores the token value and the time from which it is considered unusable. Its lifetime comes from the IAM response's `expires_in` field, minus a small margin to prevent expiry in transit.

### Masking secrets in logs

If the IAM HTTP client logs requests, add IAM-specific masking keys; otherwise the OpenID request's secret key and the response JWT appear in full in the log:

```python
from http_client import options as http_options
from grpc_client_auth import IAM_SANITIZE_KEYS, IAM_HttpClient

iam_client = IAM_HttpClient(
    "https://iam.example.com",
    http_options.with_logger(logger, sanitize_keys=IAM_SANITIZE_KEYS),
)
```

### Components

IAM HTTP clients, the token store, and the token model come from [`cloudru-qa-http-client-auth`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/http-client-auth) and are re-exported here to keep imports simple.

That library also provides `IAM_Auth` and `IAM_AsyncAuth`, which authorize the HTTP client (`httpx.Auth`) and follow a different contract. For the gRPC client, use this library's `IAM_GrpcAuth` and `IAM_GrpcAsyncAuth`.

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                          # install dependencies for all libraries from uv.lock
make test-grpc-client-auth         # tests for this library
make typecheck-grpc-client-auth    # mypy for this library
make check                         # formatting, ruff, mypy, and tests for the entire workspace
```

Tests require Docker running: the [grpcbin](https://grpcb.in/) service container is started
automatically, and the test API is generated from `proto/` before execution. IAM requests in tests
are intercepted with `pytest-httpx`.

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-grpc-client-auth PYTHON_VERSION=3.14`.

Publish a release with the git tag `grpc-client-auth/v<version>`. The tag version must match the version
in `packages/grpc-client-auth/pyproject.toml`.
