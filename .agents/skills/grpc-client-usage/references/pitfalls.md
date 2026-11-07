# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## Every call has a 60-second deadline by default

Bare grpcio sends no deadline unless you pass one. This library sets `DEFAULT_TIMEOUT_SEC = 60.0`, so a call that used to hang forever now fails with `DEADLINE_EXCEEDED` after a minute. For a genuinely long method raise it per call (`CallOptions(timeout=600)`), per client (`with_timeout`), or per subclass (`DEFAULT_TIMEOUT_SEC = 600`).

## `timeout=None` is not "unset"

`CallOptions.timeout` defaults to the sentinel `USE_CLIENT_DEFAULT`, meaning "take the client's value". An explicit `None` means "no deadline at all". The sentinel is falsy, so `if options.timeout:` conflates it with `0` and with `None` — test it with `isinstance(x, _UseClientDefault)` or just call `options.resolve_timeout(default)`.

## An async interceptor is split into several objects

`grpc.aio` routes interceptors through an `elif` chain by interface, so an object implementing all four interfaces only ever lands in the first matching chain — the other three call types pass it by. `split_async_interceptor()` therefore wraps such an interceptor into one adapter per interface before handing it to the channel.

Consequences when the client is inspected or extended:

- `client._interceptors` on an async client holds adapters, not the object you passed. The original is reachable at `adapter._impl`.
- An interceptor implementing exactly one interface is passed through untouched.
- `AsyncGRPCClient._drain_interceptors()` deduplicates by `_impl` identity, so a split interceptor is drained once, not four times.

## An async client cannot take interceptors on a ready-made channel

`AsyncGRPCClient.from_channel(channel, options.with_logger(...))` raises `ValueError`. `grpc.aio` accepts interceptors only at channel creation and has no public counterpart to `grpc.intercept_channel`. Swallowing them silently would mean auth and logging quietly not working, so it fails loudly instead.

Either build the channel yourself with `grpc.aio.insecure_channel(..., interceptors=[...])`, or use `from_addr()`. The **sync** client has no such limit — it wraps a ready channel with `grpc.intercept_channel`.

## The final async stream log is written after the call finishes

For an async stream the closing record is written from a separate task created in the call's done-callback. Two things follow:

- `await client.close()` drains those tasks — before closing the channel and again after, because unfinished streams are only torn down at close and their log tasks appear only then. Skip the close and the last record can be lost.
- A test asserting on `caplog` right after reading a stream may run before that task does. Close the client (or `await` a drain) first.

The sync client has no such delay: its counting wrapper logs inline.

## `read()` on an async stream is not counted

`_AsyncCountingCall` counts messages taken by `async for` and `collect()`. `grpc.aio`'s own `read()` goes around the wrapper, so those messages never reach the counter and the `Messages: N` field under-reports. Stick to the two supported ways of reading.

## An `authorization` in default metadata disables the auth interceptor

The auth interceptor deliberately stays out of the way when the caller supplied its own `authorization` — no token is fetched and no retry happens. It decides that by looking at the call's metadata, which by then already includes `with_default_metadata`. So combining `with_default_metadata({"authorization": ...})` with `with_auth(...)` silently disables the latter. Pick one.

## glom paths in `sanitize_keys` must use camelCase

Message bodies are rendered with `MessageToDict`, which emits protobuf field names in camelCase. A key with no separators is normalized before comparison, so `access_token` matches `accessToken` — but a **glom path** is applied verbatim. `"user.access_token"` silently matches nothing; write `"user.accessToken"`.

`MessageToDict` also runs with `always_print_fields_with_no_presence=True`, so fields left at their default value still show up in the log.

## Metadata masking does not parse paths

gRPC metadata is flat and its keys may legitimately contain dots, so `sanitize_metadata` compares whole key names, case-insensitively, with no glom involved. A key written as a path masks nothing in metadata — though the same string may still work on the body.

## Name matching for masking is by word boundary, not substring

`secret` masks `secret` and `client_secret`, but not `sec_ret`. `token` masks `token` and `refresh_token`, but not `tokenizer`. Matching is "the normalized name, or a compound name ending in `_<name>`". If a field must be masked and does not fit that shape, name it explicitly or use a glom path.

Traversal stops at 64 levels; below that everything is replaced with `<превышена глубина вложенности>` rather than emitted raw.

## Success cannot be detected by exception type

grpcio's stream call objects implement `grpc.Call` and `grpc.RpcError` simultaneously, on healthy calls too. `isinstance(outcome, grpc.RpcError)` is therefore always true for a stream and tells you nothing. Use `grpc_client.interceptors.base.outcome_code(outcome)` and compare status codes.

## Iterating a stream raises; `collect()` does not

The library's "errors become responses" rule holds for unary calls and for `collect()`. A direct `for message in stream:` re-raises the server's `grpc.RpcError`, because the messages already yielded cannot be taken back. If a test wants the failure as data, call `collect()` — it also keeps the messages that arrived before the failure.

## `collect(limit=N)` finishes as CANCELLED

Hitting the limit cancels the call, so the returned status is `CANCELLED` rather than `OK`. That is the truth of the call — the server never got to finish. Assert on the messages, not on the status, when using a limit.

## `cancel()` unlocks the final status

`cancel()` marks the stream consumed, so `status_code`, `details` and `trailing_metadata` stop raising `StreamNotConsumedError` and start reporting the cancelled call. Until then they raise — the server sends them last, and there is nothing to report.

## `with_channel_options` replaces, `with_default_metadata` accumulates

`with_channel_options` overwrites the whole tuple, so pass every grpcio option in a single call. `with_default_metadata` merges, so applying it twice keeps both sets in order of application.

## Option order matters for TLS

`with_ssl_credentials` sets `secure = True` and `with_insecure_channel` sets it to `False`. Applied together, the later one wins.

## Options run before the channel exists

The client applies options first, then builds the channel and the stub. An option that touches
`client.channel` or `client.stub` raises `AttributeError`. Use the public configuration properties
and `add_interceptor()` during option application.

Compose custom options from `with_interceptor` / `with_default_metadata`, or register an
interceptor through `client.add_interceptor()`. Private-field access and lint suppressions are unnecessary.

## A disabled logger turns the logging interceptor into a pass-through

When the logger is enabled for neither `log_level` nor `err_log_level`, the interceptor returns the continuation unchanged: no trace id is generated and streams are not wrapped for counting. Nothing breaks, but a test that expects the counting wrapper to be present will not find it.

## False alarms when reading the code

- `ClientAuth` and `AsyncClientAuth` are deliberately **not** `runtime_checkable`. Both declare `token` and `refresh`, so `isinstance` could not tell them apart and would be actively misleading. The client dispatches on whether `token()` is a coroutine function.
- `GRPCStub` and `AsyncGRPCStub` *are* `runtime_checkable`, but they only declare `__init__(channel)`; they exist to constrain the generic parameter, not to validate anything at runtime.
- `Metadata.__len__` counts unique keys while `pairs()` returns every pair, so `len(md) != len(md.pairs())` whenever a key repeats. Both are correct.
- `response.error_status` re-parses trailing metadata on each access rather than caching.
- The logging helpers swallow broad exceptions with `noqa: BLE001` on purpose: a log record is built before the request goes out, and a failure there must not take the call down with it.
