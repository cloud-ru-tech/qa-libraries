---
name: grpc-client-structlog-usage
description: Structured request/response logging for the grpc_client library — the with_structlogger option that writes every gRPC call into structlog as separate fields instead of one text line, with secret masking on by default. Use when a project imports grpc_client_structlog, when wiring structlog into a gRPC client, or when the built-in options.with_logger crashes with "object has no attribute 'isEnabledFor'". Key names are with_structlogger, sanitize_keys, use_default_sanitize_keys, status_code, messages_count, trace_id.
license: Apache-2.0
metadata:
  library-version: "1.0.0"
  source: packages/grpc-client-structlog
---

# Structured logging for grpc_client

The library exports exactly one name: `with_structlogger`. It is a `ClientOption` that replaces
`grpc_client.options.with_logger`. Instead of one text line per call, every attribute — method, body,
metadata, status — becomes its own [structlog](https://www.structlog.org) field, so logs can be
filtered and searched by field rather than by substring.

Everything else — building the client, stubs, timeouts, auth, streaming — is plain `grpc_client`.
This library adds no client of its own and no way to log outside of the option.

## Hard rules

1. Install **one** logging option. `with_structlogger` and `options.with_logger` each add their own
   interceptor; passing both logs every call twice, in two different formats.
2. Pass it as a constructor option, exactly like the built-in ones. There is no post-construction setup.
3. Put it **after** `options.with_auth(...)` so the log shows the request that actually goes out.
4. The library plugs into `options.with_log_sink` and the record types of `grpc_client`; the matching
   `cloudru-qa-grpc-client` is installed as a dependency.
5. Do not name a structlog field `message` anywhere in the pipeline: this library calls the payload
   `body` on purpose, because `EventRenamer("message")` would collide with it.
6. Do not turn off `use_default_sanitize_keys` to "clean up" the log. It unmasks passwords and tokens.
7. Levels are limited to `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`. Anything else raises
   `ValueError` when the client is built — structlog cannot write an unnamed level.

Before debugging odd output, read `references/pitfalls.md` — it covers the non-obvious behaviour.

## Why it exists

`options.with_logger` takes a stdlib logger and writes one text line per call. Feeding it a structlog
bound logger does not work: it checks the level with `logger.isEnabledFor(level)`, and a logger built
by `structlog.make_filtering_bound_logger(...)` spells that method `is_enabled_for`, so every call dies
with:

```
AttributeError: 'BoundLoggerFilteringAtDebug' object has no attribute 'isEnabledFor'.
Did you mean: 'is_enabled_for'?
```

`with_structlogger` installs a `LogSink` instead — the public extension point of `grpc-client` 2.1.
The client builds a `RequestRecord` / `ResponseRecord` and picks the level; the sink turns it into
structlog fields. The level question goes through `is_enabled_for`, and a logger that cannot answer
it — the method is missing, or it raises, as `structlog.stdlib.BoundLogger` over a
`structlog.PrintLogger` does — counts as enabled. A question about the level must never take the
call down.

## Usage

```python
import structlog
from api import orders_pb2, orders_pb2_grpc
from grpc_client import GRPCClient
from grpc_client_structlog import with_structlogger


class OrdersClient(GRPCClient[orders_pb2_grpc.OrdersStub]):
    @property
    def stub_class(self) -> type[orders_pb2_grpc.OrdersStub]:
        return orders_pb2_grpc.OrdersStub

    def get_order(self, order_id: str):
        return self.send_unary_unary_request(orders_pb2.GetOrderRequest(id=order_id), self.stub.GetOrder)


with OrdersClient.from_addr(
    "orders.example.com:443",
    with_structlogger(structlog.get_logger("orders")),
) as client:
    client.get_order("42")
```

Combines with any other option:

```python
from grpc_client import options

client = OrdersClient.from_addr(
    "orders.example.com:443",
    options.with_auth(auth),
    options.with_timeout(30),
    with_structlogger(logger, json_indent=2),
)
```

## Async client

Same option, same arguments. The sync or async interceptor is picked from the client type inside the
option, so nothing extra is configured:

```python
from grpc_client import AsyncGRPCClient


class AsyncOrdersClient(AsyncGRPCClient[orders_pb2_grpc.OrdersStub]):
    @property
    def stub_class(self) -> type[orders_pb2_grpc.OrdersStub]:
        return orders_pb2_grpc.OrdersStub

    async def get_order(self, order_id: str):
        return await self.send_unary_unary_request(orders_pb2.GetOrderRequest(id=order_id), self.stub.GetOrder)


async with AsyncOrdersClient.from_addr("orders.example.com:443", with_structlogger(logger)) as client:
    await client.get_order("42")
```

The final record of a response stream is written by a separate task, so an async client must be
closed — `close()` waits for those tasks. `async with` does it for you.

## What lands in the log

Up to two events per call, linked by `trace_id` — a level filtered out by structlog simply produces no
record, so a call can end up with one or none:

| Field | Event | Value |
|---|---|---|
| `event` | both | `grpc request sent` / `grpc response received` |
| `method` | both | `/package.Service/Method` |
| `body` | request always, response only on a successful unary answer | JSON string of the message; `<streamed content>` for a request stream |
| `metadata` | both | JSON string; **absent** when the call carried no metadata |
| `status_code` | response | status **name**: `OK`, `NOT_FOUND`, … |
| `details` | response | the service's error text; present only on a failed call |
| `messages_count` | response | number of messages read from a response stream |
| `trace_id` | both | UUID4 generated per call |

`status_code` holds the name, not the number: the name reads without a lookup table and filters
cleanly, while `5 (NOT_FOUND)` would force substring queries. `messages_count` is the only integer
field; other composite values are serialized to JSON strings. The full catalog is in
`references/fields.md`.

## Masking

Fields whose **name** is a common secret — `authorization`, `cookie`, `token`, `password`, `api_key`
and the rest of `grpc_client.utils.sanitizer.DEFAULT_SANITIZE_KEYS` — are replaced with `****` by
default, **at any depth**, and regardless of naming style (`accessToken` matches `access_token`).

Project-specific fields go into `sanitize_keys`. A key without separators is a **field name** masked
at any depth; a key with a dot, a star or brackets is a [glom](https://glom.readthedocs.io/en/latest/)
**path** applied as written:

```python
with_structlogger(logger, sanitize_keys=["x-tenant-key", "user.internal_id", "items.*.card_number"])
```

| Key | What it masks |
|---|---|
| `x-tenant-key` | a metadata key (metadata is flat, whole-key match, case-insensitive) |
| `client_secret` | a body field with that name, at any depth |
| `user.internal_id` | one nested body field |
| `items.*.card_number` | a field in every array element |

Masking never touches the message the caller receives — only the copy that goes into the log.

## Parameters

| Parameter | Type | Meaning |
|---|---|---|
| `logger` | `BoundLogger \| FilteringBoundLogger` | where to write |
| `sanitize_keys` | `Sequence[str] \| None` | field names and glom paths replaced with `****` |
| `json_indent` | `int \| None` | indent used when serializing JSON fields |
| `log_level` | `int \| None` | level of a successful record, defaults to `INFO` |
| `err_log_level` | `int \| None` | level of a failed record, defaults to `ERROR` |
| `payload_maxlength` | `int \| None` | length limit for `body`, defaults to 4096 characters |
| `use_default_sanitize_keys` | `bool` | mask common secret names at any depth, default `True` |

Levels, indent and the body limit fall back to the global `grpc_client` settings when omitted — set
them once for the whole project with `grpc_client.configure_logging(...)`. An argument passed to
`with_structlogger` wins over the global value. The `GRPC_CLIENT_*` environment variables do nothing
on their own: `configure_logging(...)` reads them when it is called, so a project that never calls it
gets library defaults regardless of the environment.

`log_level` and `err_log_level` accept **only** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. A
structlog bound logger picks its method by level name, and only those five have one. Anything else —
including a value coming from `configure_logging(...)` — raises `ValueError` while the client is being
built. The built-in `options.with_logger` accepts arbitrary integers; this is a deliberate divergence,
because the alternative is a `KeyError` from inside structlog that also stops the request from going
out at all.

## References

- `references/fields.md` — the field catalog, streaming behaviour, global defaults and env variables.
- `references/pitfalls.md` — JSON strings vs nested values, the `message` field, level filtering,
  typing of `logger`, and how the option plugs into `grpc-client`.
