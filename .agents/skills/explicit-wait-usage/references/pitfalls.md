# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## A timeout is usually reported as "no further attempt could start"

There are two distinct stop-by-time situations, and `TimeoutExpiredError.deadline_reached` tells
them apart:

- `False` — the next pause no longer fit before the deadline, so starting another attempt was
  pointless. This is the common case, and `elapsed` in the message is *below* the timeout:

  ```text
  No further attempt could start before the 30 second deadline waiting for ... (attempts: 4, elapsed: 14.000s, last result: False)
  ```

- `True` — the deadline genuinely passed, e.g. the predicate itself consumed the remaining budget
  or the sleep woke up late. Here `elapsed` can exceed the timeout:

  ```text
  Timeout of 30 seconds expired waiting for ... (attempts: 3, elapsed: 30.500s, last result: False)
  ```

A wait finishing noticeably earlier than `timeout_seconds` is therefore normal, not a bug. To use
the full budget, shrink `sleep_seconds` or cap it with `maximum_seconds`.

## The deadline never interrupts a running predicate

It is only checked between attempts. A predicate that hangs for two minutes will overrun a
30-second wait — the library cannot cancel it. Put a real per-call timeout inside the predicate
(an HTTP client timeout, for instance).

## A nested wait's failure is never retried

`WaitError` and its subclasses are excluded from `expected_exceptions` unconditionally. Otherwise
an inner wait's timeout would silently become one more failed attempt of the outer wait, and the
outer deadline would be multiplied by the inner one.

If a retry across a nested wait is genuinely what you want, turn it into a falsy result:

```python
from explicit_wait import WaitOptions

wait_until(lambda: wait_or_none(inner_condition, options=WaitOptions(timeout_seconds=5)) is not None)
```

The same rule is why `wait_or_none` swallows only *its own* stop: the driver returns the error
object instead of catching it by type, so a `TimeoutExpiredError` raised by the predicate itself
(or by a wait inside it) still propagates. `WaitCancelledError` propagates too.

## Omitting `max_attempts` and passing `None` mean different things

`WaitOptions.max_attempts` defaults to the `UNSET` marker, not to `None`:

- omitted → take the configured value;
- `None` → no attempt limit at all, even if configuration sets one.

`timeout_seconds` and `sleep_seconds` do not have this distinction — for them `None` means "take
the configured value".

## `AttemptsExhaustedError` can turn into `TimeoutExpiredError`

The terminal snapshot re-reads the clock, and if the elapsed time has reached the timeout, the
stop reason is rewritten to "time". A wait bounded by both limits can therefore raise
`TimeoutExpiredError` on the very attempt that used up `max_attempts` — and `on_timeout` fires
instead of `on_attempts_exhausted`. Catch `WaitStoppedError` when you need both.

A hook can cause this on its own: hook time counts against the deadline, so an `on_attempt` that
burns the remaining budget converts an attempts stop into a time stop.

## A synchronous wait rejects an awaitable result

A coroutine object is always truthy, so an unnoticed one would end the wait "successfully" without
the predicate body ever running. Instead the wait raises `InvalidPredicateError` (which is also a
`TypeError`) and closes the abandoned coroutine quietly.

The same applies to `AllOf` / `AnyOf` — use `AsyncAllOf` / `AsyncAnyOf`, and in a custom aggregate
call predicates only through `self.check(...)`.

`@wait_for` catches this earlier: applying it to a coroutine function raises at decoration time,
i.e. at import.

## `configured` does not cross a thread boundary

The override lives in a `contextvars` variable. Coroutines and `asyncio.to_thread` inherit it;
a `ThreadPoolExecutor` worker does not and will see the process-wide baseline instead. For
threads, use `configure`.

A task created inside a `with configured(...)` block keeps the override after the block exits —
the context is captured at task creation.

## Global configuration leaks between tests

`configure` writes to a process-wide singleton, so one test can change the behaviour of the next
and results start depending on run order. Reset it in an autouse fixture; the library does not do
it for you.

## In async code, the sync parts must not block

`async_wait_*` accepts a plain function as the predicate and calls it directly in the event loop.
All three hooks are synchronous too. `time.sleep`, file I/O, or a sync HTTP client inside any of
them stalls the whole loop, including the background tasks the wait is supposed to let run.

## `on_attempt` does not run on an unexpected exception

It fires after attempts that returned a falsy value and after attempts that ended in an *expected*
exception. An unexpected exception stops the wait immediately, so a hook used for reporting will
have no record of that final attempt.

Cancellation through `cancel_event` triggers no terminal hook at all — neither `on_timeout` nor
`on_attempts_exhausted`.

## `cancel_event` replaces `sleeper`

When a cancel event is passed, the pause runs through `Event.wait` so it can be interrupted mid
sleep. Anything passed as `sleeper` is then ignored — a fake-clock test that also passes
`cancel_event` will silently sleep for real.

## `wait_while` returns nothing

It waits for the predicate to stop being truthy and returns `None`; the final falsy value is not
handed back. When you need the value, invert the condition and use `wait_until`.

## Falsy is not the same as "false"

`0`, `""`, `[]` and `{}` all read as "not yet". A predicate returning a count keeps waiting while
that count is zero, and one returning a list keeps waiting while the list is empty — usually
convenient, occasionally a surprise. Return an explicit `True` / `None` when the value itself is
meaningless.

## `jitter` only subtracts

Each pause is drawn from `[delay * (1 - jitter), delay]`, never above the nominal value. With
`jitter=0.2` the average pause is about 10% shorter than configured, so a wait makes slightly more
attempts than the pure sequence suggests.

## False alarms when reading the code

- `Backoff.delays()` is an infinite generator, but a fresh one is built per wait, so sharing a
  single `Backoff` instance across waits (or threads) does not share the sequence.
- The library's exceptions define `__reduce__`, so they survive `pickle`, `copy` and `deepcopy`
  together with their fields, `add_note` notes and any custom subclass state. Serialization fails
  only when `last_result` or `last_exception` is itself unpicklable — worth knowing under
  `pytest-xdist`, which ships failures between processes.
- `explicit_wait` logs each attempt at `DEBUG` through the module loggers under the `explicit_wait`
  name and installs no handlers. Nothing appears until the level is lowered.
- `WaitLoop` in `explicit_wait.loop` performs no I/O of its own: it decides, while the sync and
  async drivers call the predicate and sleep. That is why the two share stop rules, backoff and
  diagnostics exactly — and why the module is internal, not part of the public API.
