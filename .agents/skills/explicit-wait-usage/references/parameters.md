# Parameter catalog and configuration

Every wait function takes a positional predicate and keyword-only runtime arguments.
Pass deadline, pause, attempt limits, description, exception filters and hooks in
`options=WaitOptions(...)`. Keep `clock`, `sleeper` and the sync-only `cancel_event` outside
that object. `configure()` and `configured()` continue to accept configuration fields directly.

## Stopping

### `timeout_seconds: float | None = None`

The deadline in seconds. `None` means "take the configured default", which starts at 64 seconds.

`math.inf` waits forever — always pair it with `max_attempts` or `cancel_event`:

```python
from explicit_wait import WaitOptions

wait_until(predicate, options=WaitOptions(timeout_seconds=math.inf, max_attempts=100))
```

Zero, a negative number, and `NaN` are rejected with `ValueError`.

The deadline is enforced *between* attempts. A predicate that is already running is never
interrupted, so one slow call can overrun the deadline — keep a per-request timeout inside the
predicate itself.

### `max_attempts: int | None = UNSET`

An attempt limit, instead of or alongside the deadline. Exceeding it raises
`AttemptsExhaustedError`. Exactly `max_attempts` attempts run: the limit is checked after an
attempt, when the next pause is planned.

```python
from explicit_wait import WaitOptions

wait_until(predicate, options=WaitOptions(max_attempts=5, sleep_seconds=2))
wait_until(predicate, options=WaitOptions(max_attempts=None))  # drop the configured limit for this wait
```

Omitting the argument means "take the configured value"; an explicit `None` means "no attempt
limit". The marker for the omitted case is `explicit_wait.UNSET`; the same distinction applies in
`configure` and `configured`. A wrong type, including `bool`, raises `TypeError`; a non-positive
integer raises `ValueError`.

If the deadline has already passed, time wins over attempts as the stop reason. The order is
fixed: deadline reached → attempts exhausted → the next pause no longer fits.

### `sleep_seconds: float | tuple | Backoff | None = None`

The pause between attempts. `None` takes the configured default, which starts at
`Backoff(initial_seconds=2, maximum_seconds=64, multiplier=2)`.

```python
from explicit_wait import WaitOptions

wait_until(predicate, options=WaitOptions(sleep_seconds=1))  # constant 1 s
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, 100)))  # 1, 2, 4, 8, 16, 32, 64, 100, 100, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, 100, 3)))  # 1, 3, 9, 27, 81, 100, 100, ...
wait_until(predicate, options=WaitOptions(sleep_seconds=(1, None)))  # 1, 2, 4, 8, 16, ... unbounded
wait_until(
    predicate,
    options=WaitOptions(sleep_seconds=Backoff(initial_seconds=1, maximum_seconds=30, multiplier=2, jitter=0.2)),
)
```

A two-item tuple implies `multiplier=2`. `None` is allowed only in the maximum position.

`Backoff` is a frozen dataclass: `initial_seconds`, `maximum_seconds=None`, `multiplier=1.0`,
`jitter=0.0`. It validates on construction, not somewhere later inside `time.sleep`:

- `initial_seconds` — a finite number greater than zero;
- `maximum_seconds` — a finite number not below `initial_seconds`, or `None`;
- `multiplier` — a finite number not below 1;
- `jitter` — a number in `[0, 1)`;
- a tuple — exactly 2 or 3 items.

`jitter` only ever *subtracts*: each pause is drawn from `[delay * (1 - jitter), delay]`. It
matters when parallel tests poll the same service — without it their requests line up into
synchronized waves. The randomness source is process-wide; `Backoff.delays(rng)` accepts an
explicit `random.Random` when a test needs determinism.

One `Backoff` instance is safe to share: every wait builds its own sequence from it.

An unbounded growing backoff (`maximum_seconds=None`, `multiplier > 1`) eventually overflows to
infinity and raises `OverflowError` telling you to set a maximum. In practice the deadline stops
the wait long before that.

## Description

### `message: str | None = None`

A human-readable description of what is being waited for, inserted into the error text as
`waiting for <message>`. Without it the predicate's `__qualname__` (or `__name__`) is used, which
for a lambda is `<lambda>` and for a `functools.partial` is `partial` — pass `message` in both
cases.

The object's address and the `repr` of its arguments are deliberately kept out of the message: an
address is useless in a report and a `repr` can leak sensitive data from `partial` arguments.

## Exceptions from the predicate

### `expected_exceptions: type[Exception] | tuple[type[Exception], ...] = ()`
### `retry_on_exception: Callable[[Exception], bool] | None = None`

`expected_exceptions` marks the predicate failures that count as "not yet". `retry_on_exception`
is consulted only for exceptions that already matched `expected_exceptions`; returning `False`
re-raises the exception out of the wait.

Never caught, whatever is listed:

- `KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError` — they are not `Exception`;
- `WaitError` and its subclasses — the library's own errors, so a nested wait's timeout cannot
  quietly become another failed attempt of the outer one.

The last expected exception ends up in the stop error's `last_exception` and in its `__cause__`.

## Hooks

### `on_attempt`, `on_timeout`, `on_attempts_exhausted: Callable[[Attempt], None] | None = None`

`on_attempt` runs after every attempt, including attempts with a falsy result and attempts that
ended in an expected exception. It does **not** run when the predicate raised something
unexpected — that wait stops immediately.

`on_timeout` runs only on a stop by time, `on_attempts_exhausted` only on a stop by attempt count.
Cancellation through `cancel_event` triggers neither.

`Attempt` is a frozen dataclass:

| Field | Meaning |
| --- | --- |
| `number` | attempt number, starting at 1 |
| `elapsed_seconds` | time since the wait started |
| `result` | the predicate's result (`None` if it ended in an expected exception) |
| `exception` | the expected exception, or `None` |
| `next_sleep_seconds` | the planned pause before the next attempt, or `None` |
| `has_no_planned_sleep` | `next_sleep_seconds is None` |

`has_no_planned_sleep` is a snapshot of the plan, not a promise of finality: an attempt can still
turn out to be the last one with a pause planned — if the wait is cancelled, if the wakeup lands
late, or if the hook itself burns the remaining budget.

Time spent in a hook counts against the deadline. The stop error and the `Attempt` handed to a
terminal hook are taken from a single clock reading made before the hook runs, so the hook's own
duration never leaks into them.

An exception raised by a hook propagates and is never treated as a predicate exception, even if
its type is listed in `expected_exceptions`.

## Cancellation

### `cancel_event: threading.Event | None = None` (sync only)

Interrupts a long wait from outside. While it is set, the pause runs through `Event.wait`, so the
`sleeper` parameter is ignored.

```python
from explicit_wait import WaitOptions

cancel = Event()  # another thread calls cancel.set()

wait_until(predicate, cancel_event=cancel, options=WaitOptions(timeout_seconds=600))
```

Cancellation raises `WaitCancelledError`, which `wait_or_none` does **not** swallow — being
cancelled is not the same as not having waited long enough.

The async functions have no such parameter: cancel the task instead.

## Time source

### `clock: Callable[[], float] = time.monotonic`
### `sleeper: Callable[[float], None] = time.sleep` (`asyncio.sleep` in the async functions)

The seam for testing code that waits, without real pauses. `clock` must behave like a monotonic
clock — the library only ever takes differences of two readings. Monotonic time is used precisely
so NTP corrections and manual clock changes cannot stretch or shrink a wait.

## Configuration

```python
from explicit_wait import WaitConfig, configure, configured, get_config, reset_config

configure(sleep_seconds=(2, 64), timeout_seconds=64)  # process-wide defaults
with configured(timeout_seconds=5):  # temporary override
    ...
get_config()  # current values
reset_config()  # back to the built-in defaults
```

`WaitConfig` is a frozen dataclass with `timeout_seconds` (default `64.0`), `backoff` (default
`Backoff(2, 64, 2)`) and `max_attempts` (default `None`). Because it is replaced whole, a
half-applied state of two inconsistent fields cannot happen, and bad values are rejected right in
the `configure` call. Concurrent `configure` calls are serialized by a lock.

Parameters left out keep their current value; `max_attempts=None` clears the limit, while omitting
`max_attempts` keeps it.

Scopes differ:

| Where | `configure` | `configured` |
| --- | --- | --- |
| Current thread | visible | visible |
| Another thread, `ThreadPoolExecutor` | visible | **not visible** |
| `asyncio` task created inside the block | visible | visible |
| `asyncio.to_thread` | visible | visible |

`configured` keeps the override in a `contextvars` variable, so coroutine contexts inherit it and
plain threads do not. A task created inside the block and outliving it keeps seeing the override —
the context is captured when the task is created.

### From the environment

Useful for raising timeouts on a slow CI without touching the code:

```python
config = WaitConfig.from_env()  # default prefix EXPLICIT_WAIT_
configure(
    timeout_seconds=config.timeout_seconds,
    sleep_seconds=config.backoff,
    max_attempts=config.max_attempts,
)
```

| Variable | Format | Example |
| --- | --- | --- |
| `EXPLICIT_WAIT_TIMEOUT_SECONDS` | number | `120` |
| `EXPLICIT_WAIT_SLEEP_SECONDS` | number, or `initial,maximum[,multiplier]` | `2,64,2` or `1,none` |
| `EXPLICIT_WAIT_MAX_ATTEMPTS` | integer | `10` |

`from_env` only reads and validates; it does not apply anything. Unset variables keep the
defaults, `none`/`null`/empty in the maximum position means "unbounded", and an unparsable value
raises `ValueError`.

## Public API surface

The package root exports the stable API only: the wait functions, the aggregates, `Backoff`,
`Attempt`, the configuration functions, `WaitConfig`, `WaitOptions`, the exceptions and the `UNSET` marker.

Type aliases and abstract base classes live in their own modules and are **not** part of the
stable API:

```python
from explicit_wait.aggregate import Aggregate, AsyncAggregate
from explicit_wait.backoff import SleepSecondsType
from explicit_wait.types import AsyncPredicate, Clock, ExceptionFilter, ExceptionsType, Predicate, Sleeper
```

A custom aggregate subclasses `Aggregate` (or `AsyncAggregate`) and implements `__call__`:

```python
class MajorityOf(Aggregate):
    """Holds when a majority of the predicates hold."""

    def __call__(self) -> bool:
        passed = sum(1 for predicate in self.predicates if self.check(predicate))
        return passed * 2 > len(self.predicates)
```

Call the predicates only through `self.check(...)`: it rejects an awaitable result that would
otherwise turn a false condition into a passing one. An aggregate needs at least one predicate —
an empty one raises `ValueError`.
