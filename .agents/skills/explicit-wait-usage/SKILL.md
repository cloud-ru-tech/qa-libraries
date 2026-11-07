---
name: explicit-wait-usage
description: Waiting for conditions in automated tests with the explicit_wait library — sync and async wait functions, backoff between attempts, attempt limits, retryable exceptions, predicate aggregation, decorators, hooks, and timeout diagnostics. Use when a test must poll until a state changes, when replacing a hand-written sleep/retry loop, or when configuring timeouts, pauses, expected exceptions, or Allure reporting in a project that imports explicit_wait. Key names are wait_until, wait_or_none, wait_while, async_wait_until, wait_for, Backoff, AllOf, AnyOf, Attempt, TimeoutExpiredError, configure.
license: Apache-2.0
metadata:
  library-version: "1.0.0"
  source: packages/explicit-wait
---

# Waiting on conditions with explicit_wait

`explicit_wait` calls a predicate over and over until it returns a truthy value, or until the
deadline runs out. Python 3.13+, no external dependencies.

Compared with a hand-written polling loop it adds exactly three things:

1. **A deadline with a backoff strategy** — the pause between attempts grows, is capped, and can
   carry jitter; a new attempt starts only if it still fits before the deadline.
2. **Self-explaining failure** — the stop error carries the attempt count, the elapsed time, the
   last result and the last exception, so a red test does not need to be re-run to be understood.
3. **One contract for sync and async** — the same parameters, the same errors, the same hooks.

Everything else (assertions, HTTP calls, fixtures) stays where it is. The predicate is a plain
function; the library never asserts anything on its own.

## Hard rules

1. Never hand-roll `while True: ... time.sleep(...)`, and never use a bare `time.sleep` as "wait
   until it is ready". Both hide the real deadline and produce a failure with no diagnostics.
2. Every parameter except the predicate is keyword-only. `wait_until(predicate, 30)` is a
   `TypeError`, not a 30-second timeout.
3. With a lambda predicate, always set `WaitOptions.message` — otherwise the error says `<lambda>`.
4. The predicate must be cheap and repeatable: it runs many times. No assertions inside it, no
   state mutation, no side effects the next attempt would trip over.
5. Never pass a coroutine function to a synchronous wait. It raises `InvalidPredicateError`; use
   the `async_*` variant.
6. `expected_exceptions` lists concrete exception classes. Never `Exception` — that turns a real
   bug into a timeout.
7. To let a wait fail silently, call `wait_or_none`. Do not wrap `wait_until` in
   `try/except TimeoutExpiredError: pass`.
8. Do not reimplement backoff, jitter, or attempt counting around a wait — set `sleep_seconds`
   and `max_attempts` in `WaitOptions`.

Before claiming a parameter cannot do something, check `references/pitfalls.md` — it documents the
behaviour that trips people up.

## Choosing a function

| Situation | Call |
| --- | --- |
| Wait for a value or condition, fail the test if it never arrives | `wait_until` |
| The condition is optional — its absence is not a failure | `wait_or_none` |
| Wait until something goes away or finishes | `wait_while` |
| Any of the above inside a coroutine | `async_wait_until` / `async_wait_or_none` / `async_wait_while` |
| A helper that is always called with waiting | `@wait_for` / `@async_wait_for` |

`wait_until` returns the predicate's own value, `wait_or_none` returns it or `None`, `wait_while`
returns nothing.

## Canonical wait (sync)

```python
from explicit_wait import WaitOptions, wait_until


def ready_order() -> Order | None:
    order = api.get_order(order_id)
    return order if order.status == "ready" else None


order = wait_until(
    ready_order, options=WaitOptions(timeout_seconds=30, sleep_seconds=(1, 5), message="order becomes ready")
)
```

The return value is the predicate's, so a wait doubles as a fetch: return the object you need and
`None` while it is not there yet. There is no second request after the wait.

A boolean predicate is fine when there is nothing to carry out:

```python
from explicit_wait import WaitOptions

wait_until(
    lambda: len(get_users()) == 2, options=WaitOptions(timeout_seconds=30, message="two users appear in the list")
)
```

**Falsy** — the values that mean "not yet": `False`, `0`, `""`, `None`, `[]`, `{}`. A predicate
that returns `0` or an empty list keeps waiting, which is usually what you want; when it is not,
return an explicit `True`/`None`.

## Canonical wait (async)

```python
from explicit_wait import WaitOptions, async_wait_until


async def order_is_ready() -> bool:
    response = await client.get(f"/orders/{order_id}")
    return response.json()["status"] == "ready"


await async_wait_until(order_is_ready, options=WaitOptions(timeout_seconds=30, message="order becomes ready"))
```

Differences from the sync version:

- the pause runs through `asyncio.sleep` and does not block the event loop;
- there is no `cancel_event` — ordinary task cancellation works, and `CancelledError` is never
  swallowed, even with `expected_exceptions=Exception`;
- the predicate may be a plain function, but then it and every hook must be non-blocking:
  `time.sleep`, file I/O, or a sync HTTP client inside them stalls the whole loop.

An awaitable returned by the predicate is always awaited, never treated as a final value.

## Parameters

Pass waiting policy as `options=WaitOptions(...)`. The fields below through the hooks belong to
that object; `cancel_event`, `clock` and `sleeper` remain separate keyword-only arguments.
`configure()` and `configured()` still accept their configuration fields directly.
The full catalog with exact semantics is in `references/parameters.md`. Summary:

| Parameter | Purpose |
| --- | --- |
| `timeout_seconds` | deadline in seconds; `None` takes the configured default (64 s), `math.inf` waits forever |
| `sleep_seconds` | pause between attempts: a number, a `(initial, maximum[, multiplier])` tuple, or a `Backoff` |
| `max_attempts` | attempt limit instead of or alongside the deadline; raises `AttemptsExhaustedError` |
| `message` | what is being waited for; goes into the error text |
| `expected_exceptions` | predicate exceptions that count as "not yet" |
| `retry_on_exception` | extra filter over those exceptions |
| `on_attempt` / `on_timeout` / `on_attempts_exhausted` | hooks receiving an `Attempt` |
| `cancel_event` | `threading.Event` that interrupts the wait from outside (sync only) |
| `clock` / `sleeper` | time source and sleep function; used to test waiting code without real pauses |

## Retrying on exceptions

`expected_exceptions` are the predicate failures that are a normal part of waiting;
`retry_on_exception` narrows them further.

```python
from explicit_wait import WaitOptions

# The service is still starting up — connection errors are expected
wait_until(service_responds, options=WaitOptions(expected_exceptions=(ConnectionError, TimeoutError)))

# Retry 5xx, surface 4xx immediately
wait_until(
    fetch_order,
    options=WaitOptions(
        expected_exceptions=httpx.HTTPStatusError,
        retry_on_exception=lambda error: isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500,
    ),
)
```

The filter is typed as receiving a plain `Exception`, so reach for class-specific fields only
after an `isinstance` check.

Anything outside `expected_exceptions` propagates unchanged, with its original traceback.
`KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError` are never caught. The library's own
errors (`WaitError` and its subclasses) are never expected either — see `references/pitfalls.md`
for how to nest one wait inside another.

## Failure diagnostics

```python
from explicit_wait import TimeoutExpiredError, WaitOptions, wait_until

try:
    wait_until(ready_order, options=WaitOptions(timeout_seconds=30, message="order becomes ready"))
except TimeoutExpiredError as error:
    error.attempts  # how many attempts ran
    error.elapsed_seconds  # how much time actually passed
    error.last_result  # what the predicate returned last
    error.last_exception  # the last expected exception, if any
    error.deadline_reached  # False = the next pause no longer fit before the deadline
```

The message is built from those same fields:

```text
No further attempt could start before the 30 second deadline waiting for order becomes ready (attempts: 4, elapsed: 14.000s, last result: False)
```

The last expected exception also becomes `__cause__`, so the traceback shows the original reason.

Hierarchy:

```text
WaitError
├── WaitStoppedError            — the condition never held
│   ├── TimeoutExpiredError     — out of time (also a built-in TimeoutError)
│   └── AttemptsExhaustedError  — max_attempts used up
├── InvalidPredicateError       — the predicate broke the contract (also a TypeError)
└── WaitCancelledError          — interrupted through cancel_event
```

Catch `WaitStoppedError` to cover both stop reasons at once. `TimeoutExpiredError` is a built-in
`TimeoutError`, so it is caught alongside `asyncio` timeouts — but **not** alongside
`httpx.TimeoutException`, which sits in a different hierarchy and needs its own `except`.

## Combining predicates

`AllOf` holds when every predicate holds at the same moment, `AnyOf` when at least one does. They
are evaluated in order, short-circuiting, and keep no state between calls — one instance is safe
to reuse across waits and threads.

```python
from explicit_wait import AllOf, AnyOf, WaitOptions, wait_until

wait_until(
    AnyOf([lambda: status() == "ready", lambda: status() == "completed"]),
    options=WaitOptions(timeout_seconds=30, message="status becomes ready or completed"),
)

ready = AnyOf([status_is("ready"), status_is("completed")]) & AllOf([cache_warm, index_built])
```

For coroutine predicates use `AsyncAllOf` / `AsyncAnyOf`. The sync aggregates reject an async
predicate with `InvalidPredicateError` instead of silently passing: a coroutine object is truthy.

## Decorators

```python
from explicit_wait import WaitOptions, wait_for


@wait_for(options=WaitOptions(timeout_seconds=30, sleep_seconds=1))
def deploy_finished() -> bool:
    return client.get("/deploy").json()["done"]


deploy_finished()  # returns once the deploy is done
```

The wrapped function's name goes into the error message; arguments are passed through. Use
`@async_wait_for` for coroutine functions — applying `@wait_for` to one raises
`InvalidPredicateError` at import time.

Reach for a decorator only when the helper is *always* awaited on. A function that is sometimes
called for its current value should stay plain and be wrapped at the call site.

## Configuration in a test suite

```python
from explicit_wait import configure, configured, reset_config

configure(sleep_seconds=(2, 64), timeout_seconds=64)  # process-wide defaults

with configured(timeout_seconds=5):  # temporary, this context only
    wait_until(predicate)
```

An argument passed to a wait always wins over configuration. Reset the global config between
tests, otherwise results start depending on test order:

```python
@pytest.fixture(autouse=True)
def reset_wait_config():
    reset_config()
    yield
    reset_config()
```

`configured` stores its override in a `contextvars` variable: coroutines inherit it, plain worker
threads do not. Scopes and environment variables are covered in `references/parameters.md`.

## Reporting

Attempts are logged to the standard `explicit_wait` logger at `DEBUG`; the library installs no
handlers of its own.

```python
logging.getLogger("explicit_wait").setLevel(logging.DEBUG)
```

Allure steps come from a hook, with no extra dependency in the library:

```python
from explicit_wait import Attempt, WaitOptions, wait_until


def report_attempt(attempt: Attempt) -> None:
    with allure.step(f"Attempt {attempt.number}: {attempt.result!r}"):
        pass


wait_until(ready_order, options=WaitOptions(on_attempt=report_attempt, message="order becomes ready"))
```

Hook time counts against the deadline, and an exception raised by a hook propagates — it is never
mixed into the predicate's expected exceptions.

## Testing code that waits

`clock` and `sleeper` replace the time source and the sleep, so a test of your own waiting helper
runs instantly and deterministically:

```python
from explicit_wait import WaitOptions


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


clock = FakeClock()
wait_until(predicate, clock=clock.monotonic, sleeper=clock.sleep, options=WaitOptions(timeout_seconds=10))
```

Both parameters are the seam the library's own tests use. Never patch `time.sleep` globally to
achieve the same effect.

## Known pitfalls

Before debugging "strange" behaviour, read `references/pitfalls.md`. It covers the stop-reason
order, why a nested wait's timeout is never retried, `max_attempts` omitted vs. `None`, the
`contextvars` scope of `configured`, and why a synchronous wait rejects awaitables.
