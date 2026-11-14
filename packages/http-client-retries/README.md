# http-client-retries

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-retries)](https://pypi.org/project/cloudru-qa-http-client-retries/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-retries)](https://pypi.org/project/cloudru-qa-http-client-retries/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-retries)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

HTTP request retries for [`cloudru-qa-http-client`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/http-client).

Network failures, timeouts, and temporary server errors are common when calling external services.
This library handles retries: add one option to the client and it resends
requests according to the configured policy. There is no need to write loops and delays manually.

Supports synchronous and asynchronous clients, with both regular and streaming requests.
Built on [`tenacity`](https://tenacity.readthedocs.io/), which provides the stop and wait
strategies.

- [Installation](#installation)
- [Skills for AI agents](#skills-for-ai-agents)
- [Quick start](#quick-start)
- [When to retry](#when-to-retry)
  - [Connection errors](#connection-errors)
  - [Limitation: request bodies must be replayable](#limitation-request-bodies-must-be-replayable)
  - [Response conditions](#response-conditions)
  - [Streaming requests](#streaming-requests)
- [Retry policy configuration](#retry-policy-configuration)
  - [Global settings](#global-settings)
  - [Per-client settings](#per-client-settings)
  - [The Retry-After header](#the-retry-after-header)
- [After the last attempt](#after-the-last-attempt)
- [Retry logging](#retry-logging)
- [Request identifiers](#request-identifiers)
- [Retrying arbitrary functions](#retrying-arbitrary-functions)
- [Parameter reference](#parameter-reference)
- [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-http-client-retries
```

Import the library as the module `http_client_retries`.

## Skills for AI agents

The package includes the [`http-client-retries-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-retries-usage/SKILL.md) skill
with examples and usage guidance for AI agents. Install the library
in your project environment, then run from the project root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-retries-usage --yes
```

For Claude Code, add `--claude`. Instructions are bundled with the library version.

## Quick start

Add the option to the client constructor to retry this client's requests on failure:

```python
from http_client import HttpClient
from http_client_retries import options

with HttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    response = client.get("/orders/42")
```

The asynchronous client works the same way:

```python
from http_client import AsyncHttpClient

async with AsyncHttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    response = await client.get("/orders/42")
```

## When to retry

### Connection errors

`with_retries_failed_requests` retries requests when the server cannot be reached:

```python
from http_client import HttpClient
from http_client_retries import options

client = HttpClient("https://api.example.com", options.with_retries_failed_requests())
```

Retries `httpx.RequestError` (including timeouts and dropped connections), `httpcore.NetworkError`,
and `httpcore.PoolTimeout`. Other errors propagate immediately without retries.

Errors that retries cannot resolve are excluded, so they do not waste
the retry budget and waiting time:

- `httpx.TooManyRedirects`: a retry follows the same redirect chain;
- `httpx.UnsupportedProtocol`: the URL scheme does not change;
- `httpx.DecodingError`: the server returns the same unreadable body.

> **Retries are not limited to idempotent methods.** `POST` and `PATCH` are retried just like
> `GET`. A network error does not prove that the server did not perform the operation: the request may have arrived,
> and the response connection may have failed. Keeping the same `X-Request-ID` across attempts prevents duplicates
> only if the server implements this behavior.

### Limitation: request bodies must be replayable

A retry resends the same request, so its body must be readable again.

| Request body | Retried |
|---|---|
| `bytes`, `str`, `json=`, `data=` | Yes |
| List or tuple of chunks | Yes |
| Open file | Yes; its position is restored before each attempt |
| `files=` with bytes or seekable files | Yes |
| `files=` with a non-seekable file | No |
| Generator or custom one-shot stream | No |

If the body cannot be replayed, the request runs **exactly once** and the original error
propagates. The library returns an error rather than sending a truncated body to the server.

```python
def stream_document():
    yield from produce_chunks()


client.send(client.client.build_request("POST", "/documents", content=stream_document()))
```

To retry such an upload, buffer the body in memory (`content=b"".join(...)`) or
pass a file object.

The `with_retries_if` condition still runs once for these requests. Since the request cannot
be replayed, its response is returned as is, even if the condition requested a retry.

### Response conditions

`with_retries_if` retries while your condition returns `True`:

```python
from httpx import Response


def is_throttled(response: Response) -> bool:
    return response.status_code == 429


client = HttpClient("https://api.example.com", options.with_retries_if(is_throttled))
```

The condition can be any function that takes an `httpx.Response` and returns a `bool`.

Combine these options with each other and with `http_client` options:

```python
from http_client import options as http_options

client = HttpClient(
    "https://api.example.com",
    options.with_retries_failed_requests(),
    options.with_retries_if(lambda response: response.status_code >= 500),
    http_options.with_timeout(5.0),
)
```

Both options share a retry loop and attempt budget: with `stop_after_attempt(5)`,
at most five requests reach the server, even when network failures
alternate with 5xx responses. Option order does not affect the result.

Set policy parameters once per client, with each parameter specified in exactly one option.
Specifying the same parameter in both options makes the constructor raise `ValueError`. The library
deliberately avoids comparing values semantically: tenacity strategies have no equality comparison,
and treating hook functions as identical could silently discard one of them.

### Streaming requests

No extra setup is needed: both options cover `client.stream(...)`
and `client.stream_request(...)`.

```python
with HttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    with client.stream("GET", "/large-file.zip") as response:
        for chunk in response.iter_bytes(chunk_size=8192):
            handle(chunk)
```

The `with_retries_if` condition runs on the open stream before reading the response body.

Only **opening** the stream is retried. If the connection fails while reading the body,
inside `iter_bytes()` or `aiter_bytes()`, the error propagates immediately without retries. Some data
has already been received, so restarting would be unsafe. Implement resuming downloads yourself
using the `Range` header.

## Retry policy configuration

### Global settings

`configure` sets process-wide defaults:

```python
from http_client_retries import Config

from http_client_retries import configure
from tenacity import stop_after_attempt, wait_exponential_jitter

configure(
    options=Config(
        stop=stop_after_attempt(5), wait=wait_exponential_jitter(initial=1, max=64, jitter=1), reraise=False
    ),
)
```

Without `configure`, the defaults in the [parameter reference](#parameter-reference) apply:
up to five attempts with exponential backoff and random jitter.

Strategies come from tenacity; see
[stop](https://tenacity.readthedocs.io/en/stable/api.html#stop-functions) and
[wait](https://tenacity.readthedocs.io/en/stable/api.html#wait-functions).

### Per-client settings

To give one client a custom policy, pass it directly to the option:

```python
from http_client_retries import RetryOverrides

from tenacity import stop_after_attempt

payments = HttpClient(
    "https://payments.internal",
    options.with_retries_failed_requests(
        overrides=RetryOverrides(stop=stop_after_attempt(2), reraise=True),
    ),
)

catalog = HttpClient(
    "https://catalog.internal",
    options.with_retries_failed_requests(),
)
```

Here, `payments` makes at most two attempts, while `catalog` uses the global configuration.
Unspecified parameters also come from the global configuration, including changes made by
`configure` after the client was created.

### The Retry-After header

When the server sends `Retry-After` (usually with 429 or 503), the delay comes from that header.
Both formats are supported: seconds and an HTTP date. The value is capped by
`max_retry_after`. Invalid headers are ignored in favor of the regular wait strategy.

Since the header arrives in a response, only a policy that retries based on responses can use it.
If a client retries **only** network errors, `respect_retry_after`
and `max_retry_after` have no effect.

Disable it globally or for one client:

```python
from http_client_retries import Config, RetryOverrides

configure(options=Config(respect_retry_after=False))

client = HttpClient(
    "https://api.example.com", options.with_retries_failed_requests(overrides=RetryOverrides(respect_retry_after=False))
)
```

## After the last attempt

When attempts are exhausted, behavior depends on `reraise`:

| `reraise` | Exception raised |
|---|---|
| `False` (default) | `tenacity.RetryError`; the original error is available through `err.last_attempt.exception()` |
| `True` | The original error, such as `httpx.ConnectError` |

```python
from tenacity import RetryError

try:
    response = client.get("/orders/42")
except RetryError as err:
    original = err.last_attempt.exception()
```

`reraise=True` is useful when the caller already handles `httpx` exceptions:

```python
from http_client_retries import RetryOverrides

import httpx

client = HttpClient(
    "https://api.example.com", options.with_retries_failed_requests(overrides=RetryOverrides(reraise=True))
)

try:
    response = client.get("/orders/42")
except httpx.ConnectError:
    ...
```

## Retry logging

`log_retry_error_hook` logs the reason for each retry: method, URL, and error:

```python
from http_client_retries import Config

import logging

from http_client_retries import configure, log_retry_error_hook

configure(options=Config(before_sleep_hook=log_retry_error_hook(logging.getLogger("http"))))
```

Replace it with a custom function that receives a
[`RetryCallState`](https://tenacity.readthedocs.io/en/stable/api.html#tenacity.RetryCallState):

```python
from http_client_retries import Config


def report_attempt(retry_state):
    metrics.increment("http.retry", attempt=retry_state.attempt_number)


configure(options=Config(before_sleep_hook=report_attempt))
```

An asynchronous hook requires an asynchronous client: synchronous `tenacity` cannot await it,
so this combination raises `TypeError` rather than silently skipping calls.

Disable the hook for one client by passing `before_sleep_hook=None` directly to the option;
the global configuration stays unchanged.

## Request identifiers

All attempts of one request share the same `X-Request-ID` and `Traceparent`. Find retries
in logs by their shared identifier; the server can also use it to prevent duplicates.
No configuration is needed:

```python
client = HttpClient(
    "https://api.example.com",
    http_options.with_autogenerated_request_id(),
    options.with_retries_failed_requests(),
)
```

Identifiers set manually by the caller also stay the same across retries.

The rule is simple: **the identifier belongs to the request object**. Different requests get different
values; all sends of one `httpx.Request`, including retries, share one identifier.

There is one limitation. Built-in httpx authentication schemes (`BasicAuth`, `DigestAuth`, or a function)
reuse the request object, preserving the identifier. A custom `httpx.Auth` that
creates a **new** `Request` instead of modifying the original gets a new identifier on each
attempt: the library does not copy headers to the new request. If the server relies
on `X-Request-ID` to prevent duplicates, set the header yourself in this case.

## Retrying arbitrary functions

To retry calls outside `http_client`, use the decorators directly.

`retry_if_failed` retries connection errors:

```python
import httpx

from http_client_retries import retry_if_failed


@retry_if_failed
def fetch_status():
    return httpx.get("https://api.example.com/health")
```

`retry_if` retries based on a result condition:

```python
from http_client_retries import retry_if


@retry_if(lambda response: response.status_code == 503)
def fetch_report():
    return httpx.get("https://api.example.com/report")
```

Both also support asynchronous functions:

```python
@retry_if_failed
async def fetch_status():
    async with httpx.AsyncClient() as client:
        return await client.get("https://api.example.com/health")
```

The decorators use the global configuration from `configure`.

## Parameter reference

Accepted by both `configure` and the two options.

| Parameter | Default | Purpose |
|---|---|---|
| `stop` | `stop_after_attempt(5)` | When to stop retrying |
| `wait` | `wait_exponential_jitter(initial=1, max=64, jitter=1)` | Delay between attempts |
| `before_sleep_hook` | `None` | Function called before each retry |
| `reraise` | `False` | Raise the original error instead of `RetryError`; does not affect response-condition retries |
| `respect_retry_after` | `True` | Use the `Retry-After` delay; requires a response-based retry policy |
| `max_retry_after` | `60.0` | Maximum `Retry-After` delay in seconds |

`get_config()` returns an immutable snapshot: its fields cannot be reassigned. `configure()` replaces
the entire configuration in one assignment. Immutability is shallow: tenacity strategies themselves
remain mutable objects, so do not change their fields after passing them to `configure()`.
Create a new strategy instead.

`reraise` applies only to network-error retries, where an original exception exists
to raise again. When a response condition exhausts the retry budget, there is no original exception:
`RetryError` is always raised, and the last response is available through `err.last_attempt.result()`.

## Development

This library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make
and [`checkmake`](https://github.com/checkmake/checkmake);
run the commands from the repository root:

```shell
make sync                            # dependencies for all libraries from uv.lock
make test-http-client-retries        # tests for this library
make typecheck-http-client-retries   # mypy for this library
make check                           # formatting, Ruff, mypy, and tests for the whole suite
```

Tests run on Python 3.13 and 3.14. Each version uses a separate environment:
`make sync test-http-client-retries PYTHON_VERSION=3.14`.

Create a release with the Git tag `http-client-retries/v<version>`. The tag version must match
the version in `packages/http-client-retries/pyproject.toml`.
