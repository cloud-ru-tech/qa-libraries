# Responses, streams, metadata and errors

## `GRPCResponse[T]`

Returned by both unary send methods, and by `collect()` on a stream (there `T` is `list[Message]`).

| Member | Notes |
|---|---|
| `ok` | `status_code is grpc.StatusCode.OK` |
| `status_code` | never `None` — an unreadable status becomes `UNKNOWN` |
| `details` | server-supplied text, `""` when absent |
| `message()` | the response message; raises `MessageUndefinedError` when the call carried none |
| `initial_metadata` | `Metadata` received before the body |
| `trailing_metadata` | `Metadata` received after the body; `metadata` is an alias |
| `error` | the original `grpc.RpcError`, `None` on success |
| `error_status` | `ErrorStatus` parsed from trailing metadata, `None` when the service sent none |
| `raise_for_status()` | raises `ResponseStatusError` unless OK; returns `self`, so it chains |
| `with_parser(fn)` | wraps into `GRPCResponseWithParser` |

Constructed by `from_call(message, call)` on success and `from_error(error, message=None)` on failure. Metadata is read defensively: an implementation that refuses to hand it over yields an empty `Metadata` rather than an exception.

### `GRPCResponseWithParser[TMsg, TResult]`

Same read-only surface plus `parse()`, which runs the parser over `message()` — so it raises `MessageUndefinedError` on an empty response, same as `message()`. It does not expose `with_parser()` again.

```python
def parser(msg: example_pb2.Order) -> OrderModel:
    return OrderModel(id=msg.id, total=msg.total)


return self.send_unary_unary_request(request, self.stub.GetOrder).with_parser(parser)
```

## `GRPCStreamResponse[T]`

Lazy: messages are read as they arrive and are not buffered. The call stays open until the stream is drained or cancelled.

```python
with client.watch_orders(request) as stream:  # cancels on exit
    for message in stream:
        if message.is_last:
            break
```

```python
response = client.watch_orders(request).collect()  # a plain GRPCResponse[list[Order]]
assert response.status_code == grpc.StatusCode.OK
for message in response.message():
    ...
```

| Member | Available |
|---|---|
| `__iter__` | once; a second pass raises `StreamConsumedError` |
| `initial_metadata` | any time |
| `status_code`, `details`, `ok`, `trailing_metadata` | only after the stream is consumed or cancelled — otherwise `StreamNotConsumedError` |
| `cancel()` | any time; a no-op once consumed |
| `collect(limit=None)` | once; `limit=0` cancels without reading, a negative limit raises `ValueError` |

The final status and trailing metadata are a property of a *finished* call — the server sends them last — which is why they are gated behind consumption rather than returning a placeholder.

**Iteration and `collect()` differ on failure.** Iterating re-raises the server's `grpc.RpcError`; `collect()` turns it into a `GRPCResponse` carrying the error status *and* the messages that arrived before it, which is usually what a test wants:

```python
response = client.watch_orders(request).collect()
assert response.status_code == grpc.StatusCode.RESOURCE_EXHAUSTED
assert len(response.message()) == 3  # arrived before the failure
```

`collect(limit=N)` cancels the call once N messages are in, so the resulting status is `CANCELLED`, not `OK`.

## `AsyncGRPCStreamResponse[T]`

Same model, asynchronous. The send method itself is awaited, then the stream is read with `async for`:

```python
stream = await client.watch_orders(request)
async with stream:
    async for message in stream:
        ...
```

Differences from the sync stream:

- `status_code()`, `details()`, `initial_metadata()`, `trailing_metadata()` are **coroutines**, not properties;
- there is no `ok` — compare `await stream.status_code()` yourself;
- `collect()` is a coroutine;
- `asyncio.CancelledError` during iteration also cancels the underlying call and marks the stream consumed, then propagates. Swallowing it would break `asyncio.timeout` and clean shutdown;
- when the client itself cancelled the stream (`cancel()`, or `collect(limit=...)` hitting the limit), `collect()` reports `CANCELLED` without querying the call — asking a cancelled call for its status would raise.

## `Metadata`

`Mapping[str, MetadataValue]` where `MetadataValue = str | bytes`, preserving order and repeated keys.

| Member | Behaviour |
|---|---|
| `md["key"]` | first value for the key, case-insensitive; `KeyError` when absent |
| `md.get_all("key")` | every value for the key, in arrival order; `()` when absent |
| `md.pairs()` | every pair including repeats — `items()` collapses them |
| `len(md)`, `iter(md)` | count and iterate **unique** keys, yielding the first spelling seen |

Binary values are allowed only for keys ending in `-bin`; that is a gRPC rule, and grpcio enforces it.

Accepted request forms (`MetadataType`): a `Mapping[str, MetadataValue]`, a sequence of `(key, value)` pairs, or a `Metadata` instance.

Merge order for one call, front to back:

1. `with_default_metadata` on the client, in the order the options were applied;
2. `CallOptions.metadata`;
3. the `metadata=` argument of the send method;
4. anything interceptors add — they run on the channel, so they always append last.

Helpers in `grpc_client.metadata`: `as_metadata_items`, `merge_metadata`, `contains_key` (case-insensitive), `aio_metadata_items` (normalizes the `grpc.aio` metadata type, which iterates as pairs but is not a `Sequence`).

## `ErrorStatus` — rich error details

Services put the interesting part of a failure into `google.rpc.Status`, transported in the `grpc-status-details-bin` trailing metadata key. The library parses it lazily off `response.error_status`.

```python
from google.rpc import error_details_pb2

response = client.get_order(request)

if response.error_status:
    response.error_status.code  # numeric google.rpc.Code
    response.error_status.message  # service-supplied text
    response.error_status.details  # tuple of parsed detail messages

    bad_request = response.error_status.of_type(error_details_pb2.BadRequest)
    violations = response.error_status.all_of_type(error_details_pb2.BadRequest)
```

`error_status` is `None` when the service sent nothing, when the key is missing, or when the payload does not parse — the failed response itself is still intact, so a broken details blob never breaks the call.

Detail types are resolved through the protobuf symbol registry, which is populated by importing the generated `*_pb2` modules. A type nobody imported stays a `google.protobuf.Any`, and `of_type` will not find it. Import the module that defines the detail message.

## Exceptions

All inherit from `GRPCClientError`.

| Exception | Raised when |
|---|---|
| `MessageUndefinedError` | `message()` / `parse()` on a response that carries no message; exposes `status_code` and `details` |
| `ResponseStatusError` | `raise_for_status()` on a non-OK response; exposes `status_code` and `details` |
| `StreamConsumedError` | reading or collecting a stream that was already read |
| `StreamNotConsumedError` | asking a stream for its final status or trailing metadata before it finished |

Server-side failures are **not** in this table: they arrive as a status code on the response. The exceptions above are all about misusing the client.

Two failures do escape as raw grpcio errors rather than becoming a response:

- iterating a stream directly (see above) — `collect()` is the converting path;
- a `grpc.RpcError` that does not implement `grpc.Call`, which the sync client re-raises: without the `Call` interface neither the status code nor the metadata can be recovered, so turning it into a response would mean inventing one.
