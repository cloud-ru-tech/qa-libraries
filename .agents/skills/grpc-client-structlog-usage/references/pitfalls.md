# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## The built-in option crashes on a filtering bound logger

This is the whole reason the library exists. `grpc_client.options.with_logger` calls
`logger.isEnabledFor(level)`. A logger from `structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(...))`
has `is_enabled_for` instead, so every call dies with:

```
AttributeError: 'BoundLoggerFilteringAtDebug' object has no attribute 'isEnabledFor'
```

`with_structlogger` asks through `is_enabled_for` and falls back to "enabled" when the logger cannot
answer. "Cannot answer" covers two cases: the method is absent, and the method **raises**. The second
one is real — `structlog.stdlib.BoundLogger` declares both spellings but forwards them to the logger
underneath, so
`structlog.configure(wrapper_class=structlog.stdlib.BoundLogger, logger_factory=structlog.PrintLoggerFactory())`
gives a logger that writes fine and explodes on the level question. Under the built-in option that
combination kills every call.

The check itself is not optional: building the body means `MessageToDict` plus masking plus
`json.dumps`, and doing that for a record nobody will keep is wasteful.

What is **not** guarded is the write itself. If the structlog processor chain raises, the exception
comes out of the call — unlike stdlib `logging`, structlog does not swallow errors of its own
pipeline, and hiding them would mean losing every record silently.

## The payload field is `body`, never `message`

Many pipelines end with `structlog.processors.EventRenamer("message")`, which moves `event` into
`message`. A field of the library's own named `message` would be overwritten by the event text and
disappear. So the payload is `body`, matching `http_client_structlog`. Do not rename it back.

## Composite fields are JSON strings, not nested values

`body` and `metadata` reach structlog already serialized. In a console renderer that reads fine; under
`JSONRenderer` the field is a string with escaped quotes inside the outer JSON:

```json
{"event": "grpc request sent", "body": "{\"login\": \"morgan\"}"}
```

This is deliberate — nested structures would collide with field names of the surrounding application
context and would explode the index of a log store. If a collector must see the body as an object,
parse that string in a structlog processor of your own.

Consequence for `json_indent`: it puts real newlines inside those strings. Useful when a human reads
the console, harmful for a line-based collector — leave it unset in production.

## structlog does its own level filtering

`log_level` is just the level handed to `.log()`. If structlog (or the stdlib logging behind it) is
configured above that level, the record is dropped and the option looks broken. Lowering `log_level`
to `DEBUG` requires lowering the structlog threshold as well.

When **both** `log_level` and `err_log_level` are filtered out, the interceptor skips everything —
it does not even generate a `trace_id` or wrap the stream for counting.

## Only five log levels exist

`logging` lets you invent levels — `logger.log(15, ...)` is fine, and `options.with_logger` passes it
through. structlog does not: a bound logger maps the level to a method **name**, and only
`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` have one. Both `structlog.stdlib.BoundLogger` and
the classes from `make_filtering_bound_logger` raise `KeyError: 15`.

So `with_structlogger` validates the two levels while the client is built and raises `ValueError`
instead. The check runs on the **resolved** values, so a bad level in
`grpc_client.configure_logging(...)` or in `GRPC_CLIENT_LOG_LEVEL` is caught too. Without it the
failure would land on the first RPC, during the request record — before the call goes out, so the
request would never be sent.

## `details` is the one field that is never masked

`body` and `metadata` go through the sanitizer. `details` — the service's error text — does not, and
`payload_maxlength` does not trim it either. It is a free-form string, and masking matches field names
and glom paths, so there is nothing to match on. `sanitize_keys=["details"]` does **not** help: that
list applies inside the payload, not to the record's own fields.

A service that does `context.abort(INVALID_ARGUMENT, f"bad token {token}")` leaks it. The built-in
`options.with_logger` behaves identically, so this is not a regression — but it is the one channel
where a secret reaches the log untouched.

## The final record of an unread sync stream comes from a grpcio thread

`_CountingCall` registers the finish log through grpcio's `add_done_callback`. When the caller is not
sitting inside `next()` — the stream was abandoned, hit its deadline, or the channel closed — grpcio
runs that callback on one of its **own** threads, and the record is written there. So the processor
chain and the sink get called from a thread the application never set up: they have to be thread-safe.

`structlog.contextvars` do survive that hop — verified on grpcio 1.83 for an abandoned stream, an
expired deadline, and a context bound in a worker thread: the finish record carried the same
`request_id` as the request record, even though a plain `threading.Thread` sees no contextvars at all.
Do not rely on it blindly across grpcio upgrades, but it is not a known hole today.

## Two logging options log everything twice

`with_structlogger` and `options.with_logger` each append their own interceptor and neither is aware
of the other. Both installed means two records per call in two different formats. Pick one.

## Order matters relative to auth

Interceptors run in the order they are added. Put `with_structlogger` **after**
`options.with_auth(...)`, otherwise the logged metadata is the request before the token was injected.

## `logger` accepts both bound logger flavours

The parameter type is `structlog.stdlib.BoundLogger | structlog.typing.FilteringBoundLogger`. The two
are not interchangeable for a type checker — the stdlib one spells the level check `getEffectiveLevel`
and the filtering protocol spells it `get_effective_level` — so neither alone would accept the other,
hence the union. At runtime the option only calls `.log(level, event, **fields)` and
`is_enabled_for(level)`, which any bound logger provides; a logger built by some other wrapper class
still works, it just needs a `cast` to type-check.

## The counter and the async client

`messages_count` counts what the caller actually read. On the async client, `call.read()` goes past
the interceptor's wrapper, so those messages are not counted; async iteration (`async for`,
`AsyncGRPCStreamResponse.collect()`) is counted correctly.

## The async stream record arrives after the call, not after the last message

It is written by a task scheduled from the call's completion callback. Assert on it only after
`await client.close()` (or after leaving `async with`), which drains those tasks. A test that checks
the stream record right after `collect()` is racy.

## Masking never touches the message the caller receives

Every masking pass builds a copy. The response message still holds the real values — `****` exists
only in the log. Do not use the option as a way to strip secrets out of a payload.

## `sanitize_keys` mixes two mechanisms

A key without separators is a **name** matched at any depth; a key with a dot, star or brackets is an
exact **glom path**. `password` masks the field everywhere, `user.password` masks exactly one place.
For metadata neither applies literally: metadata is flat, so the whole key is compared,
case-insensitively, and a glom-looking key is matched as a plain key name.

A path that matches nothing is skipped silently, so a typo shows up as an unmasked field, not as an
error.

## A broken glom path costs the whole body

Unlike `http_client_structlog`, where each field is protected separately, the gRPC body is one unit:
if masking or serialization raises, `body` becomes `<не удалось подготовить тело сообщения>` and no
part of the payload is logged. The call itself still goes out — the log is built defensively, so a
logging failure never breaks a request. `metadata` is unaffected and stays correct.

## How the option plugs into grpc-client

`with_structlogger` installs `StructlogSink` through `options.with_log_sink` — the public extension
point added in `grpc-client` 2.1. Nothing here subclasses an interceptor.

The split is: `grpc-client` decides **what happened** — it intercepts all four call types, wraps
response streams to count messages, reads the outcome, builds a `RequestRecord` / `ResponseRecord`
and picks the level. `StructlogSink` decides **how it is written** — masking, JSON serialization,
truncation, and the field names.

`ResponseRecord` covers three outcomes with one shape, and the sink tells them apart the same way
the built-in `TextLogSink` does:

| Outcome | `status_code` | `message` | `messages_count` | Parser used |
|---|---|---|---|---|
| unary success | `OK` | the response | `None` | `parse_response` |
| stream finished | `OK` | `None` | count | `parse_stream_response` |
| any failure | the error code | `None` | count for streams, `None` for unary | `parse_error` |

Everything the sink uses is public: `RequestRecord` / `ResponseRecord` / `resolve_log_levels` from
`grpc_client`, `sanitize` / `sanitize_metadata` from `grpc_client.utils.sanitizer`, and
`LogFormat` / `BytesEncoder` / the marker constants from `grpc_client.utils.logutils`.

## Only `with_structlogger` is public API

`__init__` exports that one name. `sink`, `parser` and the constants inside them are internal
and can move. Filter logs by the event strings if you must, but do not import them.
