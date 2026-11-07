# Pitfalls

Cases where the library deliberately does not retry, plus the traps in testing retry code.

## A non-replayable body disables retries silently

`body_rewinder` inspects the request before the first attempt. If the body is a generator, a custom
one-shot stream, or a `files=` part backed by a non-seekable file, the call is made **once** and the
original exception propagates unwrapped — no `RetryError`, no log line from `before_sleep_hook`,
nothing in the metrics.

This is intentional: httpx reuses the same `Request` object across attempts, so a consumed generator
would raise `StreamConsumed` and a spent file object would quietly send an empty body that the server
happily answers with 200.

So "my retries never fire on this upload" is almost always a body problem, not a policy problem.
Buffer the content or pass a seekable file.

## Only stream *opening* is retried

`with client.stream(...)` retries `__enter__`. Once the response is open and you are pulling chunks,
a mid-body `ReadError` escapes immediately. Bytes have already been handed to the caller; replaying
from zero would corrupt them. Resumption belongs to the caller, via `Range`.

## `reraise=True` does nothing for condition-based retries

`reraise` re-raises the exception from the last attempt. When the budget is exhausted because a
`with_retries_if` condition kept returning `True`, the last attempt *succeeded* — there is no
exception. The caller always gets `RetryError`, with the response at `err.last_attempt.result()`.

## `Retry-After` is invisible to a network-only policy

The header arrives in a response. A client configured with `with_retries_failed_requests()` alone
retries on exceptions, where no response exists, so `respect_retry_after` and `max_retry_after` never
come into play. Add a `with_retries_if` condition to make them matter.

## Four `RequestError` subclasses are never retried

`TooManyRedirects`, `UnsupportedProtocol`, `DecodingError`, `LocalProtocolError`. They are formally
`RequestError`, but the retry would follow the identical redirect chain / URL scheme / malformed
body and fail identically, having spent the whole budget and all the sleeps.

## An async `before_sleep_hook` on a sync client raises `TypeError`

Synchronous `tenacity.Retrying` does not await the hook's return value, so a coroutine would be
created, never awaited, and the hook body would never run. The library refuses the pairing up front
instead. This catches two shapes:

- `async def hook(retry_state)` — rejected when the retrying object is built;
- a plain `def hook` that *returns* an awaitable — rejected on the first call, after closing the
  coroutine to suppress the `never awaited` warning.

Async clients accept both sync and async hooks.

## The same parameter in two options is a `ValueError`

```python
from http_client_retries import RetryOverrides

HttpClient(
    "https://api.example.com",
    options.with_retries_failed_requests(overrides=RetryOverrides(stop=stop_after_attempt(2))),
    options.with_retries_if(is_throttled, overrides=RetryOverrides(stop=stop_after_attempt(2))),  # ValueError: stop
)
```

Identical values, and even the very same object, are still rejected. The merge only asks "was this
set?", because tenacity strategies have no `__eq__` and comparing hook functions by identity would
silently drop one of two distinct callables. Declare each parameter in one option.

## Options only work from the constructor

`http_client` composes send/stream decorators once, inside `__init__`. Register them through
constructor options. Public registration methods reject calls after construction with `RuntimeError`;
applying a new retry option to an already constructed client is unsupported.

## A custom `httpx.Auth` can break identifier stability

Every attempt reuses one `Request`, so `X-Request-ID` and `Traceparent` stay constant — including
under `BasicAuth`, `DigestAuth`, and callable auth, which all mutate the request in place.

An `Auth` subclass that *constructs a new* `httpx.Request` in `auth_flow` produces a fresh
identifier on every attempt. The library does not copy headers into a request it did not create.
If the server deduplicates by `X-Request-ID`, set the header yourself in such a scheme.

## Testing: mock transports hide replay bugs

`httpx.MockTransport` (and `pytest_httpx`) call `request.read()`, which buffers the body. After that
every body looks replayable, and a test that should catch a truncated retry passes.

To test replay behaviour, write a bare `httpx.BaseTransport` / `httpx.AsyncBaseTransport` that reads
`request.stream` the way a real transport does.

## Testing: `httpx_mock.get_requests()` returns the same object per attempt

Since retries reuse one `Request`, post-hoc header assertions see only the final state — a test
asserting "the identifier is stable" passes even when it is not. Capture headers at send time, from
inside the transport or a request hook.

## False alarms when reading the code

- `request_body.py` imports private httpx classes (`IteratorByteStream`, `MultipartStream`) inside a
  `try/except ImportError`. If a future httpx moves them, the tuples fall back to empty and every
  unbuffered body is classified as non-replayable. That is a deliberate fail-closed: no retries
  beats truncated data.
- A rejected response carries `extensions["http_client_retries.rejected"] = True`. It is an internal
  marker, set so the user predicate is not evaluated twice per attempt, and it is **removed** again
  when a response is accepted — response objects can be reused between attempts, and a stuck marker
  would retry an accepted response.
- `_reject` closes a rejected response when it is still open. That matters for `send(stream=True)`,
  which returns an unread response — without the close the connection leaks for every retried
  attempt.
- `Config` is frozen, but the tenacity strategies inside it are not. `get_config()` is a safe
  snapshot of *which* strategies are in use, not of their internal state.
