# Parameters and public API

## Installation

```shell
pip install cloudru-qa-http-client-retries
```

Requires Python 3.13+. `cloudru-qa-http-client`, `httpx` and `tenacity` are installed as dependencies.

## The policy parameters

The same six policy fields belong to `Config` for global defaults and `RetryOverrides` for
per-client overrides. Pass them as `configure(options=Config(...))` and
`with_retries_*(overrides=RetryOverrides(...))`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `stop` | `StopBaseT` | `stop_after_attempt(5)` | when to give up |
| `wait` | `WaitBaseT` | `wait_exponential_jitter(initial=1, max=64, jitter=1)` | pause between attempts |
| `before_sleep_hook` | `Callable[[RetryCallState], None \| Awaitable[None]] \| None` | `None` | called before every retry |
| `reraise` | `bool` | `False` | raise the original exception instead of `RetryError` |
| `respect_retry_after` | `bool` | `True` | take the pause from the `Retry-After` header |
| `max_retry_after` | `float` | `60.0` | upper bound, in seconds, for a `Retry-After` pause |

`stop` and `wait` come from tenacity —
[stop functions](https://tenacity.readthedocs.io/en/stable/api.html#stop-functions),
[wait functions](https://tenacity.readthedocs.io/en/stable/api.html#wait-functions).
Jitter is part of the default on purpose: without it every client in the fleet retries in lockstep
after a shared outage.

## `configure(...)` — global defaults

```python
from http_client_retries import Config, configure

configure(
    options=Config(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=64, jitter=1),
        before_sleep_hook=None,
        reraise=False,
        respect_retry_after=True,
        max_retry_after=60.0,
    )
)
```

Fields omitted from `Config(...)` use built-in defaults. `configure()` replaces the whole policy;
it does not patch the current one. Call it once at start-up.

`max_retry_after` must be a finite non-negative number; anything else raises `ValueError`.

The swap is a single assignment, so a concurrent request sees either the old policy in full or the
new one in full, never a mixture. Clients read the config **per request**, so calling `configure()`
after clients are built still takes effect.

## `get_config() -> Config`

An immutable snapshot: `Config` is a frozen dataclass, and its fields cannot be reassigned.

The immutability is shallow — the tenacity strategies inside are ordinary mutable objects. Never
mutate a strategy after handing it to `configure()`; build a new one instead.

## The options

```python
from http_client_retries import RetryOverrides, options
from tenacity import stop_after_attempt

options.with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(3)))
options.with_retries_if(is_throttled, overrides=RetryOverrides(max_retry_after=15.0))
```

The `overrides` argument and all `RetryOverrides` fields are keyword-only. A field left `UNSET`
means "inherit from the global config at request time"; it exists separately from `None` because
`RetryOverrides(before_sleep_hook=None)` disables the hook for that client.

`with_retries_if` may be passed several times; the conditions are OR-ed, and the request is retried
when any of them returns `True`.

Both names are also importable straight from the package root:
`from http_client_retries import with_retries_failed_requests, with_retries_if`.

## `Retry-After`

When the server sends `Retry-After` (typically with 429 or 503), that value replaces the `wait`
strategy for the next pause, clamped by `max_retry_after`.

| Header value | Result |
|---|---|
| `120` | 120 s, clamped to `max_retry_after` |
| `Wed, 21 Oct 2026 07:28:00 GMT` | seconds until that moment; a past date means 0 |
| a negative number | ignored — the spec requires a non-negative delay |
| unparsable or empty | ignored, the `wait` strategy applies |

The header lives in a response, so only a policy that can retry **on a response** ever sees it.
On a client with network-error retries only, `respect_retry_after` and `max_retry_after` are inert.

Public helpers:

- `parse_retry_after(value: str, now: datetime | None = None) -> float | None` — parses both formats;
  a naive `now` is treated as UTC.
- `wait_retry_after(fallback: WaitBaseT, maximum: float)` — the tenacity wait strategy itself, usable
  standalone. `maximum` must be finite and non-negative.

## Exported names

| Name | Kind | Purpose |
|---|---|---|
| `configure`, `get_config` | functions | global policy |
| `Config`, `RetryOverrides` | frozen dataclasses | resolved policy and per-client overrides |
| `with_retries_failed_requests`, `with_retries_if` | client options | the normal entry point |
| `retry_if_failed`, `retry_if` | decorators | retry any sync or async callable |
| `retry_stream_if_failed`, `retry_stream_if` | decorators | sync `stream_request`-shaped context managers |
| `async_retry_stream_if_failed`, `async_retry_stream_if` | decorators | async variants |
| `log_retry_error_hook(logger)` | hook factory | logs method, URL, `trace_id`, and the error |
| `parse_retry_after`, `wait_retry_after` | helpers | `Retry-After` handling |
| `RETRYABLE_EXCEPTIONS` | tuple | `(httpx.RequestError, httpcore.NetworkError, httpcore.PoolTimeout)` |
| `RetryPolicy` | dataclass | the per-client policy object |

Submodules `options`, `decorators`, `policy`, `retry_after`, `sleep_hooks` are exported too, so both
`from http_client_retries import options` and `from http_client_retries.options import ...` work.

## `RetryPolicy`

Held on the client under `_http_client_retries_policy` and created by whichever option runs first;
that same option registers the send and stream decorators. Fields: `retry_on_network_errors: bool`,
`conditions: list[ResponseCondition]`, `overrides: RetryOverrides`.

Constructing one by hand is only useful for the standalone decorators —
`send_decorator(RetryPolicy(...))` and the two `*_stream_decorator` factories in
`http_client_retries.decorators` accept a policy directly.

`RetryOverrides.merge(other)` is what raises `ValueError` when two options declare the same
parameter. It compares by "was it set at all", never by value: tenacity strategies define no
equality, and shallow-comparing hook functions would silently drop one of two distinct callables.

## `log_retry_error_hook(logger)`

Writes one `ERROR` record per retry:

```
Failed http request [POST] https://api.example.com/orders with id=<trace_id>: ConnectError: ...
```

`id` is `request.extensions["trace_id"]`, the identifier `http_client`'s logging option uses to link
a request to its response, or `<none>` when logging is not enabled. When the retried callable had no
`httpx.Request` among its arguments the record degrades to `Failed http request: <error>`.

For a rejected response (a condition asked for the retry) the error reads
`ServiceUnavailable: status code = <code>` — there is no exception in that case.
