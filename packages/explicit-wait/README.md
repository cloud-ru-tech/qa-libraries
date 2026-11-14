# Explicit waits

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-explicit-wait)](https://pypi.org/project/cloudru-qa-explicit-wait/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-explicit-wait)](https://pypi.org/project/cloudru-qa-explicit-wait/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-explicit-wait)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Functions for explicit waits in automated tests: synchronous and asynchronous, with timeout
diagnostics and no external dependencies.

- [Explicit waits](#explicit-waits)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Quick start](#quick-start)
  - [Wait functions](#wait-functions)
  - [Parameters](#parameters)
    - [`timeout_seconds`](#timeout_seconds)
    - [`sleep_seconds`](#sleep_seconds)
    - [`max_attempts`](#max_attempts)
    - [`message`](#message)
    - [`expected_exceptions` and `retry_on_exception`](#expected_exceptions-and-retry_on_exception)
    - [`on_attempt`, `on_timeout`, and `on_attempts_exhausted`](#on_attempt-on_timeout-and-on_attempts_exhausted)
    - [`cancel_event`](#cancel_event)
    - [`clock` and `sleeper`](#clock-and-sleeper)
  - [Timeout diagnostics](#timeout-diagnostics)
  - [Exception hierarchy](#exception-hierarchy)
  - [Combining predicates](#combining-predicates)
  - [Asynchronous waits](#asynchronous-waits)
  - [Decorators](#decorators)
  - [Configuration](#configuration)
  - [Logging and reports](#logging-and-reports)
  - [Extending the library](#extending-the-library)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-explicit-wait
```

Import the library as the `explicit_wait` module.

## Skills for AI agents

The package includes the [`explicit-wait-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/explicit-wait-usage/SKILL.md) skill
with examples and usage rules for AI agents. Install the library
in your project environment, then run this from its root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill explicit-wait-usage --yes
```

For Claude Code, add `--claude`. The instructions are shipped with the library version.

## Quick start

```python
from explicit_wait import WaitOptions

from explicit_wait import wait_until


def get_users() -> list[User]:
    """Get the list of users."""
    response = client.send(...)
    return response.model()


# Wait until the list contains 2 users
wait_until(
    lambda: len(get_users()) == 2,
    options=WaitOptions(timeout_seconds=30, message="the list contains 2 users"),
)
```

All parameters except the predicate are keyword-only. This makes calls unambiguous
and prevents accidentally passing the timeout as the sleep interval.

## Wait functions

| Function | Behavior | Returns |
| --- | --- | --- |
| `wait_until` | waits until the predicate returns a non-falsy value | predicate value |
| `wait_or_none` | the same, but does not raise on failure | predicate value or `None` |
| `wait_while` | waits until the predicate stops returning a truthy value | `None` |
| `async_wait_until` | `wait_until` in an event loop | predicate value |
| `async_wait_or_none` | `wait_or_none` in an event loop | predicate value or `None` |
| `async_wait_while` | `wait_while` in an event loop | `None` |
| `wait_for` | decorator: calls the function until its first truthy result | function value |
| `async_wait_for` | the same for a coroutine function | function value |

**Falsy values** are values that act as false in boolean operations:
`False`, `0`, `""`, `None`, `[]`, `{}`.

## Parameters

Pass settings for a wait through `options=WaitOptions(...)`. You can reuse this object.

### `timeout_seconds`

Maximum wait time in seconds. `None` uses the configuration value
(64 seconds by default). To wait forever, request it explicitly:

```python
from explicit_wait import WaitOptions

import math

wait_until(predicate, options=WaitOptions(timeout_seconds=math.inf, max_attempts=100))
```

Zero, negative values, and `NaN` raise `ValueError`.

### `sleep_seconds`

Pause between attempts. Set it with a number, a tuple, or a `Backoff` object:

```python
from explicit_wait import WaitOptions

from explicit_wait import Backoff, wait_until

# Constant 1-second interval
wait_until(predicate, options=WaitOptions(sleep_seconds=1))

# Grow by a factor of 2 up to the maximum: 1, 2, 4, 8, 16, 32, 64, 100, 100, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, 100)))

# Grow by a specified factor: 1, 3, 9, 27, 81, 100, 100, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, 100, 3)))

# Grow without an upper bound: 1, 2, 4, 8, 16, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, None)))

# Explicit strategy with jitter: randomly subtract up to 20% from each pause
wait_until(
    predicate,
    options=WaitOptions(
        sleep_seconds=Backoff(
            initial_seconds=1,
            maximum_seconds=30,
            multiplier=2,
            jitter=0.2,
        ),
    ),
)
```

Jitter helps when parallel tests poll the same service: without it,
their requests arrive in synchronized waves.

Values are checked when the strategy is created, rather than later inside `time.sleep`:

- initial interval — a finite number greater than zero;
- maximum — a finite number at least as large as the initial interval, or `None`;
- multiplier — a finite number greater than or equal to 1;
- jitter — a number in the range `[0, 1)`;
- tuple — exactly 2 or 3 items; `None` is allowed only for the maximum.

### `max_attempts`

Limit the number of attempts instead of, or together with, the time limit. Exhausting
attempts raises `AttemptsExhaustedError`.

```python
from explicit_wait import WaitOptions

wait_until(predicate, options=WaitOptions(max_attempts=5, sleep_seconds=2))

# Remove the configured limit for one wait
wait_until(predicate, options=WaitOptions(max_attempts=None))
```

An omitted argument means "use the configuration value"; explicit `None` means "no limit
on the number of attempts". The same distinction applies to `configure` and `configured`.

If the deadline has already passed, time is the stopping reason, rather than attempts: first
check the deadline, then the attempt limit, then whether the next pause fits.

### `message`

A readable description of what you are waiting for. It appears in the error message, so a failed test
explains itself. Without `message`, the predicate function's name is used; for a lambda this
is not informative, so always provide `message` with lambdas.

The object address and argument `repr` are excluded from the message, keeping useless
addresses and sensitive data from `functools.partial` arguments out of logs.

### `expected_exceptions` and `retry_on_exception`

`expected_exceptions` lists predicate exceptions treated as a normal part of waiting.
`retry_on_exception` adds a filter: retry or propagate the error.

```python
from explicit_wait import WaitOptions

# Wait for the service to start, ignoring connection errors
wait_until(predicate, options=WaitOptions(expected_exceptions=(ConnectionError, TimeoutError)))

# Retry only 5xx responses and propagate 4xx errors immediately
wait_until(
    predicate,
    options=WaitOptions(
        expected_exceptions=httpx.HTTPStatusError,
        retry_on_exception=lambda error: isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500,
    ),
)
```

The filter receives the exception as `Exception`, so use `isinstance` before accessing
class-specific fields: the types of `expected_exceptions` and `retry_on_exception`
are not linked.

An exception outside `expected_exceptions` propagates unchanged with its original
traceback. `KeyboardInterrupt`, `SystemExit`, and `asyncio.CancelledError` are
never caught.

The library's own errors (`WaitError` and its subclasses) are never expected, regardless of
`expected_exceptions`. Otherwise, a nested wait's timeout would silently become another
failed attempt in the outer wait. To retry a nested wait anyway, convert its error
to a falsy result inside the predicate:

```python
from explicit_wait import WaitOptions

wait_until(lambda: wait_or_none(inner_condition, options=WaitOptions(timeout_seconds=5)) is not None)
```

### `on_attempt`, `on_timeout`, and `on_attempts_exhausted`

Hooks receive an `Attempt` object:

```python
from explicit_wait import WaitOptions

from explicit_wait import Attempt, wait_until


def log_attempt(attempt: Attempt) -> None:
    print(f"attempt {attempt.number}: {attempt.result!r}, elapsed {attempt.elapsed_seconds:.1f}s")


wait_until(predicate, options=WaitOptions(on_attempt=log_attempt))
```

| `Attempt` field | Value |
| --- | --- |
| `number` | attempt number, starting at 1 |
| `elapsed_seconds` | time since the wait started |
| `result` | predicate result (`None` if it raised an expected exception) |
| `exception` | expected predicate exception or `None` |
| `next_sleep_seconds` | pause before the next attempt, or `None` if none is planned |
| `has_no_planned_sleep` | whether no pause is planned at the time of the decision |

`has_no_planned_sleep` is a snapshot of the plan, not a guarantee that the attempt is final:
an attempt with a planned pause may still be the last if the wait is canceled externally,
wakes up late, or the hook itself uses up the remaining time.

`on_attempt` runs after each attempt, including falsy results and expected exceptions.
It does not run if the predicate raises an unexpected exception:
that stops the wait immediately.

`on_timeout` runs only when the time limit stops the wait; `on_attempts_exhausted` runs only
when `max_attempts` is exhausted. Neither runs on cancellation through `cancel_event`.

Time spent in hooks counts toward the deadline: if `on_attempt` uses up the remaining
budget, the planned pause is skipped and the elapsed deadline becomes the stopping reason,
even if attempts had already been exhausted before the hook. Exception diagnostics and the
`Attempt` passed to the terminal hook come from a single clock reading before the hook,
so they do not include the hook's own duration.

An exception raised by the hook itself propagates and is **not** treated as a predicate
exception, even if its type is listed in `expected_exceptions`.

### `cancel_event`

Allows a long wait to be canceled externally. When set, the pause between attempts
uses `Event.wait`, so the `sleeper` parameter is not used.

```python
from explicit_wait import WaitOptions

from threading import Event

cancel = Event()
# from another thread: cancel.set()

wait_until(predicate, options=WaitOptions(timeout_seconds=600), cancel_event=cancel)
```

Cancellation raises `WaitCancelledError`. `wait_or_none` does not suppress it: cancellation
is different from failing to satisfy the condition.

The asynchronous version needs no separate parameter: standard task cancellation works.

### `clock` and `sleeper`

Time source and sleep function. These let you test waiting code without real pauses.
Defaults are `time.monotonic` and `time.sleep` (`asyncio.sleep` in asynchronous functions).

## Timeout diagnostics

The stopping error carries everything needed to investigate a failed test:

```python
from explicit_wait import WaitOptions

from explicit_wait import TimeoutExpiredError, wait_until

try:
    wait_until(
        lambda: get_order().status == "ready",
        options=WaitOptions(timeout_seconds=30, message="the order becomes ready"),
    )
except TimeoutExpiredError as error:
    print(error.attempts)  # number of attempts
    print(error.elapsed_seconds)  # actual elapsed time
    print(error.last_result)  # last predicate result
    print(error.last_exception)  # last expected exception
```

The error message uses the same fields. Most waits stop because the next pause
would no longer fit before the deadline; in this case, `deadline_reached` is `False`:

```text
No further attempt could start before the 30 second deadline waiting for the order becomes ready (attempts: 4, elapsed: 14.000s, last result: False)
```

If the deadline has actually passed, for example because the predicate used up the time or the wait
woke up late, the message differs and `deadline_reached` is `True`:

```text
Timeout of 30 seconds expired waiting for the order becomes ready (attempts: 3, elapsed: 30.500s, last result: False)
```

If attempts raised an expected exception, it appears in both the message and `__cause__`,
so the traceback shows the original cause:

```text
No further attempt could start before the 30 second deadline waiting for the service responds (attempts: 4, elapsed: 14.002s, last exception: ConnectionError: [Errno 61] Connection refused)
```

An overly long `repr` of the last result is truncated to keep the report compact.

## Exception hierarchy

```text
WaitError
├── WaitStoppedError            — the condition was not satisfied
│   ├── TimeoutExpiredError     — time expired (also inherits from built-in TimeoutError)
│   └── AttemptsExhaustedError  — max_attempts exhausted
├── InvalidPredicateError       — predicate violated the contract (also inherits from TypeError)
└── WaitCancelledError          — wait interrupted through cancel_event
```

`InvalidPredicateError` inherits from `TypeError`, so it can be caught as usual, and from
`WaitError`, so `expected_exceptions` cannot accidentally swallow it.

All exceptions support `pickle`, `copy`, and `deepcopy`, including their fields, `add_note`
notes, and custom subclass state. An exception cannot be serialized if its
`last_result` or `last_exception` cannot be serialized.

`TimeoutExpiredError` inherits from built-in `TimeoutError`, so one `except TimeoutError`
catches timeouts from both this library and `asyncio`. httpx timeouts are outside this
hierarchy: `httpx.TimeoutException` inherits from `httpx.TransportError` and must be
caught separately:

```python
except (TimeoutError, httpx.TimeoutException):
    ...
```

The `deadline_reached` field on `TimeoutExpiredError` distinguishes between a deadline
that has actually passed and a next pause that could not fit before it, making another attempt pointless.

## Combining predicates

`AllOf` is true when **all** predicates are true at once; `AnyOf` is true when at least
one is true. Predicates run in the listed order with short-circuit evaluation.

```python
from explicit_wait import WaitOptions

from explicit_wait import AllOf, AnyOf, wait_until

wait_until(
    AnyOf([lambda: get_status() == "ready", lambda: get_status() == "completed"]),
    options=WaitOptions(timeout_seconds=30, message="the status becomes ready or completed"),
)

wait_until(
    AllOf([users_loaded, settings_loaded, profile_loaded]),
    options=WaitOptions(timeout_seconds=60, message="all data is loaded"),
)
```

Combinations keep no state between calls: reuse the same object across waits
and call it from multiple threads. Build compositions with operators:

```python
ready = AnyOf([status_is("ready"), status_is("completed")]) & AllOf([cache_warm, index_built])
```

For asynchronous predicates, use `AsyncAllOf` and `AsyncAnyOf`: they await each predicate
and also use short-circuit evaluation:

```python
from explicit_wait import WaitOptions

from explicit_wait import AsyncAllOf, async_wait_until

await async_wait_until(
    AsyncAllOf([order_is_paid, invoice_is_issued]),
    options=WaitOptions(timeout_seconds=30, message="the order is paid and the invoice is issued"),
)
```

Synchronous `AllOf` and `AnyOf` reject asynchronous predicates with `TypeError`:
a coroutine is truthy, so accepting it would turn a false condition into a success.

## Asynchronous waits

The pause between attempts uses `asyncio.sleep` without blocking the event loop, so
background tasks continue between attempts. A predicate may be a coroutine
or a regular function. Regular functions run directly in the event loop, so they and all hooks
(`on_attempt`, `on_timeout`, `on_attempts_exhausted`) must be non-blocking:
`time.sleep`, file I/O, or a synchronous HTTP client inside them blocks the entire loop.

If the predicate returns an awaitable, it is always awaited rather than treated as the final value.

```python
from explicit_wait import WaitOptions

from explicit_wait import async_wait_until


async def order_is_ready() -> bool:
    response = await client.get(f"/orders/{order_id}")
    return response.json()["status"] == "ready"


await async_wait_until(order_is_ready, options=WaitOptions(timeout_seconds=30, message="the order becomes ready"))
```

Cancellation works as usual: `asyncio.CancelledError` is not caught, so
`task.cancel()` interrupts the wait even with `expected_exceptions=Exception`.

## Decorators

```python
from explicit_wait import WaitOptions

from explicit_wait import wait_for


@wait_for(options=WaitOptions(timeout_seconds=30, sleep_seconds=1))
def deploy_finished() -> bool:
    return client.get("/deploy").json()["done"]


deploy_finished()  # returns when deployment finishes
```

The decorated function's name appears in the error message. For coroutine functions, use
`async_wait_for`.

## Configuration

```python
from explicit_wait import configure, configured, get_config, reset_config

# Defaults for all waits in the process
configure(sleep_seconds=(2, 64), timeout_seconds=64)

# Temporary override within the block, restored even if an exception occurs
with configured(timeout_seconds=5):
    wait_until(predicate)

# Current values and reset to original defaults
get_config()
reset_config()
```

Configuration is an immutable `WaitConfig` object. It cannot be left partly applied
with inconsistent fields, and invalid values are rejected as soon as you call
`configure`. An explicit wait function argument always overrides the configuration.
Concurrent `configure` calls from different threads are serialized with a lock,
so updates are not lost.

`configure` and `configured` have different scopes:

| Scope | `configure` | `configured` |
| --- | --- | --- |
| Current thread | visible | visible |
| Another thread, `ThreadPoolExecutor` | visible | **not visible** |
| `asyncio` task created inside the block | visible | visible |
| `asyncio.to_thread` | visible | visible |

`configured` stores the override in `contextvars`, so coroutine contexts inherit it,
but regular threads do not. A task created inside the block that outlives it
keeps the override: its context is captured when the task is created.

Reset global configuration between tests, otherwise results can depend
on the test execution order:

```python
import pytest
from explicit_wait import reset_config


@pytest.fixture(autouse=True)
def reset_wait_config():
    reset_config()
    yield
    reset_config()
```

Read values from environment variables to increase timeouts on slow CI
without changing the code:

```python
from explicit_wait import WaitConfig, configure

config = WaitConfig.from_env()  # default prefix is EXPLICIT_WAIT_
configure(
    timeout_seconds=config.timeout_seconds,
    sleep_seconds=config.backoff,
    max_attempts=config.max_attempts,
)
```

| Variable | Format | Example |
| --- | --- | --- |
| `EXPLICIT_WAIT_TIMEOUT_SECONDS` | number | `120` |
| `EXPLICIT_WAIT_SLEEP_SECONDS` | number or `initial,maximum[,multiplier]` | `2,64,2` or `1,none` |
| `EXPLICIT_WAIT_MAX_ATTEMPTS` | integer | `10` |

## Logging and reports

The library logs each attempt at `DEBUG` level using the standard logger and does not
configure handlers itself:

```python
import logging

logging.getLogger("explicit_wait").setLevel(logging.DEBUG)
```

Build Allure steps with a hook; no separate dependency is needed:

```python
from explicit_wait import WaitOptions

import allure
from explicit_wait import Attempt, wait_until


def report_attempt(attempt: Attempt) -> None:
    with allure.step(f"Attempt {attempt.number}: {attempt.result!r}"):
        pass


wait_until(predicate, options=WaitOptions(on_attempt=report_attempt, message="the order becomes ready"))
```

## Extending the library

The package root exports only the stable API: wait functions, combinations, `Backoff`,
`Attempt`, configuration, exceptions, and the `UNSET` marker. Helper type aliases and
abstract base classes are available from their own modules and are not part of the stable API:

```python
from explicit_wait.aggregate import Aggregate, AsyncAggregate
from explicit_wait.backoff import SleepSecondsType
from explicit_wait.types import AsyncPredicate, Clock, ExceptionFilter, ExceptionsType, Predicate, Sleeper
```

To implement a custom combination, inherit from `Aggregate` (or `AsyncAggregate`) and implement `__call__`:

```python
from explicit_wait.aggregate import Aggregate


class MajorityOf(Aggregate):
    """True when most predicates are true."""

    def __call__(self) -> bool:
        passed = sum(1 for predicate in self.predicates if self.check(predicate))
        return passed * 2 > len(self.predicates)
```

Call predicates in a custom combination only through `self.check(...)`: it rejects
asynchronous results that would otherwise silently turn a false condition into a success.

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                        # install dependencies for all libraries from uv.lock
make test-explicit-wait          # tests for this library
make typecheck-explicit-wait     # mypy for this library
make check                       # formatting, ruff, mypy, and tests for the entire workspace
```

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-explicit-wait PYTHON_VERSION=3.14`.

Publish a release with the git tag `explicit-wait/v<version>`. The tag version must match the version
in `packages/explicit-wait/pyproject.toml`.
