---
name: http-client-retries-usage
description: Retrying HTTP requests in projects built on the http_client library — constructor options that retry on connection errors or on a condition over the response, a global tenacity-based policy, Retry-After support, and standalone retry decorators. Use when a client needs to survive network flapping, 429/503 throttling, or flaky upstreams, and when tuning attempt budgets, backoff, retry logging, or diagnosing why a request was not retried. Key names are with_retries_failed_requests, with_retries_if, configure, retry_if_failed, retry_if, log_retry_error_hook.
license: Apache-2.0
metadata:
  library-version: "1.0.0"
  source: packages/http-client-retries
---

# Retrying requests with http_client_retries

`http_client_retries` mounts [`tenacity`](https://tenacity.readthedocs.io/) into an `http_client`
client through the `with_send_decorator` / `with_stream_decorator` extension points. It adds three
things:

1. **Two constructor options** — `with_retries_failed_requests()` (retry on connection errors) and
   `with_retries_if(condition)` (retry while a predicate over the response says so).
2. **A policy**, global via `configure()` and overridable per client, covering attempt budget,
   backoff, `Retry-After`, and the before-sleep hook.
3. **Standalone decorators** for retrying functions that have nothing to do with `http_client`.

Everything else — stop/wait strategies, `RetryError`, `RetryCallState` — is plain `tenacity`.
Do not wrap it in your own abstractions.

## Hard rules

1. Never hand-roll a retry loop, backoff, or circuit breaker on top of `http_client`. Mount this
   library instead.
2. Both options are passed to the **constructor**. Adding a decorator after the client is built has
   no effect — `http_client` composes decorators once, in `__init__`.
3. A client has exactly **one** policy. Both options fill the same instance, so one shared attempt
   budget covers network errors and response conditions together.
4. Each policy parameter is declared in exactly **one** option. Declaring `stop` (or any other) in
   both raises `ValueError` at construction time — even when the two values are the same object.
5. A request whose body cannot be replayed is sent **once**, silently. See
   [Replayable bodies](#replayable-bodies) before enabling retries on uploads.
6. An async `before_sleep_hook` on a sync client raises `TypeError`. Match the hook to the client.

Before concluding that retries "do not work", read `references/pitfalls.md` — it covers every case
where the library deliberately declines to retry.

## Quick start

```python
from http_client import HttpClient
from http_client_retries import options

with HttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    response = client.get("/orders/42")
```

Async is identical apart from the base class and `await`:

```python
from http_client import AsyncHttpClient

async with AsyncHttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    response = await client.get("/orders/42")
```

Both options cover `send` **and** `stream_request`, sync and async. Nothing extra to wire up.

## What gets retried

### Connection errors

`with_retries_failed_requests()` retries `httpx.RequestError` (timeouts, connection resets, read
errors), `httpcore.NetworkError`, and `httpcore.PoolTimeout`.

Four `RequestError` subclasses are excluded, because a retry would produce the identical outcome
while burning the whole budget: `TooManyRedirects`, `UnsupportedProtocol`, `DecodingError`,
`LocalProtocolError`.

**Retries are not restricted to idempotent methods.** `POST` and `PATCH` are retried like `GET`.
A network error does not prove the server did not act — the request may have arrived and only the
response been lost. A stable `X-Request-ID` across attempts protects against duplicates only if the
server implements that semantics.

### A condition over the response

```python
import httpx
from http_client import HttpClient
from http_client_retries import options


def is_throttled(response: httpx.Response) -> bool:
    return response.status_code == 429


client = HttpClient("https://api.example.com", options.with_retries_if(is_throttled))
```

The condition is any `Callable[[httpx.Response], bool]`. It is called once per attempt; an exception
raised inside it closes the response and propagates.

### Combining them

```python
from http_client import options as http_options

client = HttpClient(
    "https://api.example.com",
    options.with_retries_failed_requests(),
    options.with_retries_if(lambda response: response.status_code >= 500),
    http_options.with_timeout(5.0),
)
```

One loop, one budget: with `stop_after_attempt(5)` the transport sees at most five requests no matter
how network failures and 5xx responses interleave. Option order does not matter.

## Replayable bodies

A retry re-sends the same `httpx.Request` object, so its body must be readable more than once.

| Body | Retried |
|---|---|
| `bytes`, `str`, `json=`, `data=` | yes |
| a list or tuple of chunks | yes |
| an open file object | yes — the position is restored before every attempt |
| `files=` holding bytes or seekable files | yes |
| `files=` holding a non-seekable file | no |
| a generator, or any custom one-shot stream | no |

When the body is not replayable the request runs **exactly once** and the original error propagates
unwrapped. The library would rather surface the failure than put a truncated body on the wire — a
consumed generator raises `StreamConsumed` on the second attempt, and a spent file object silently
sends nothing at all.

To make such an upload retryable, buffer it (`content=b"".join(chunks)`) or pass a real file object.

A `with_retries_if` condition still runs for these requests — once. The response is then handed back
as is, even if the condition asked for a retry.

## Streaming

```python
with HttpClient("https://api.example.com", options.with_retries_failed_requests()) as client:
    with client.stream("GET", "/large-file.zip") as response:
        for chunk in response.iter_bytes(chunk_size=8192):
            handle(chunk)
```

Only **opening** the stream is retried. The `with_retries_if` condition is evaluated on the open
stream, before the body is read; a rejected response is closed immediately instead of holding the
connection until the outer `with` exits.

An error raised while consuming the body — inside `iter_bytes()` / `aiter_bytes()` — propagates
without a retry. Part of the data has already been delivered, so restarting is not safe. Implement
resumption yourself with a `Range` header.

## Policy

Global defaults for the process:

```python
from http_client_retries import Config, configure
from tenacity import stop_after_attempt, wait_exponential_jitter

configure(
    options=Config(stop=stop_after_attempt(5), wait=wait_exponential_jitter(initial=1, max=64, jitter=1), reraise=False)
)
```

Those are also the built-in defaults — up to five attempts with exponential backoff and jitter.

Pass per-client settings in `overrides=RetryOverrides(...)`; anything left out keeps following the global
config, including changes made by a later `configure()` call:

```python
from http_client_retries import RetryOverrides

payments = HttpClient(
    "https://payments.internal",
    options.with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2), reraise=True)),
)
```

Full parameter list, defaults, and `Retry-After` handling: `references/parameters.md`.

## After the last attempt

| `reraise` | What is raised |
|---|---|
| `False` (default) | `tenacity.RetryError`; the original error is at `err.last_attempt.exception()` |
| `True` | the original exception, e.g. `httpx.ConnectError` |

`reraise` applies only to retries driven by exceptions. When the budget is exhausted on a response
condition there is nothing to re-raise: the result is always `RetryError`, and the last response is
available at `err.last_attempt.result()`.

## Logging retries

```python
import logging

from http_client_retries import Config, configure, log_retry_error_hook

configure(options=Config(before_sleep_hook=log_retry_error_hook(logging.getLogger("http"))))
```

Any callable taking a
[`RetryCallState`](https://tenacity.readthedocs.io/en/stable/api.html#tenacity.RetryCallState) works
as a hook. Pass `overrides=RetryOverrides(before_sleep_hook=None)` into an option to disable
the global hook for one client without touching the global config.

## Request identifiers

Every attempt of one request carries the same `X-Request-ID` and `Traceparent`, so retries are
greppable by a single id and the server can use it for deduplication. This needs no configuration
beyond the `http_client` options that generate them:

```python
client = HttpClient(
    "https://api.example.com",
    http_options.with_autogenerated_request_id(),
    options.with_retries_failed_requests(),
)
```

The rule: **the identifier belongs to the request object.** One caveat about custom `httpx.Auth`
schemes is in `references/pitfalls.md`.

## Retrying arbitrary functions

```python
import httpx
from http_client_retries import retry_if, retry_if_failed


@retry_if_failed
def fetch_status():
    return httpx.get("https://api.example.com/health")


@retry_if(lambda response: response.status_code == 503)
def fetch_report():
    return httpx.get("https://api.example.com/report")
```

Both detect coroutine functions automatically and work on `async def` too. They read the global
`configure()` policy — there is no per-decorator override. Stream variants: `retry_stream_if_failed`,
`retry_stream_if`, `async_retry_stream_if_failed`, `async_retry_stream_if`.

## Reference

- `references/parameters.md` — every parameter, its default, `Retry-After` rules, the public API surface.
- `references/pitfalls.md` — every situation where a retry does not happen, and the traps in testing retry code.
