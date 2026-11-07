# Field catalog and configuration

Two records per gRPC call. Field sets differ; `method`, `metadata` and `trace_id` are shared.

## Request — `grpc request sent`

| Field | Type | Value |
|---|---|---|
| `method` | `str` | full method name, `/package.Service/Method` |
| `body` | `str` | JSON object of the request message after masking |
| `metadata` | `str` | JSON object of the request metadata; **absent** when there was none |
| `trace_id` | `str` | UUID4 generated for this call |

The record is written **before** the call goes out, so it exists even when the call never reaches the
service.

## Response — `grpc response received`

The same event name covers a successful unary answer, a failed call, and the end of a response
stream. Which fields appear tells them apart:

| Field | Type | Present when |
|---|---|---|
| `method` | `str` | always |
| `status_code` | `str` | always — the status **name**, e.g. `OK`, `DEADLINE_EXCEEDED` |
| `body` | `str` | successful unary answer only |
| `details` | `str` | failed call only; may be an empty string if the service said nothing |
| `messages_count` | `int` | stream calls only, including a failed stream |
| `metadata` | `str` | trailing metadata was non-empty |
| `trace_id` | `str` | always — matches the request record |

`messages_count` is the only integer field. Everything composite (`body`, `metadata`) is serialized
into a JSON string, not passed as a nested dict.

A successful record is written at `log_level` (default `INFO`), a failed one at `err_log_level`
(default `ERROR`). "Failed" means any status other than `OK`, including `CANCELLED` after the caller
cancelled the stream itself.

## Streams

The body of a stream never lands in the log — reading it for the sake of logging would change the
behaviour of the call.

| Call type | Request `body` | Response fields |
|---|---|---|
| unary-unary | the message | `body` |
| unary-stream | the message | `messages_count` |
| stream-unary | `<streamed content>` | `body` |
| stream-stream | `<streamed content>` | `messages_count` |

`messages_count` counts messages actually read by the caller. Two consequences:

- a stream that is abandoned half-way logs the count read up to that point, with the status the call
  ended on (usually `CANCELLED` or `DEADLINE_EXCEEDED`);
- on the async client, messages taken with `call.read()` instead of async iteration bypass the
  counter — `grpc.aio` reads them past the interceptor's wrapper. `AsyncGRPCStreamResponse` iterates,
  so `collect()` and `async for` count correctly.

The final stream record is written when the call finishes, not when the last message is read. On the
async client that happens in a separate task, which `AsyncGRPCClient.close()` waits for.

## Body rendering

The message is converted with `MessageToDict(always_print_fields_with_no_presence=True)`, masked, and
serialized with `ensure_ascii=False`. So field names appear in protobuf JSON style (`accessToken`, not
`access_token`), and unset scalar fields appear with their default values.

A protobuf `bytes` field is what `MessageToDict` makes of it — **Base64**, not text: `b"text"` is
logged as `"dGV4dA=="`. The `<двоичные данные>` marker never appears in a body; it belongs to binary
metadata values (`-bin` keys), which reach the JSON encoder as raw `bytes` and are decoded as UTF-8
when they can be.

Two failure modes replace the body:

| `body` holds | Meaning |
|---|---|
| `<не удалось подготовить тело сообщения>` | conversion, masking or serialization raised |
| `... <обрезано>` at the end | the JSON exceeded `payload_maxlength` (4096 characters by default) |

Both constants live in `grpc_client.utils.logutils` (`PAYLOAD_UNAVAILABLE`, `TRUNCATION_SUFFIX`).
A broken glom path in `sanitize_keys` is the usual cause of the first one — the request itself still
goes out, because the log is built defensively.

## Metadata rendering

Metadata is masked, then grouped into a JSON object. A repeated key keeps all of its values as a
list:

```json
{"x-region": ["ural", "siberia"], "authorization": "****"}
```

A dict would have kept only the last value, and the log would no longer match what was sent.
The field is omitted entirely when there is no metadata — an empty JSON object is never written.

## Masking mechanics

One pass over the payload, driven by the merged key list (`sanitize_keys` plus, unless disabled,
`DEFAULT_SANITIZE_KEYS`):

| Key shape | Applies to | Matches |
|---|---|---|
| no separators (`password`) | body | a field with that name at **any** depth |
| dot / star / brackets (`user.token`) | body | that glom path only |
| any | metadata | the whole key, case-insensitive — metadata is flat, paths are not parsed |

Name matching normalizes to snake_case, so `accessToken`, `AccessToken` and `access_token` all match
`access_token`, and a composite name ending in a secret (`client_secret`, `user_password`) matches
too. Substring matching is deliberately not used — it would mask a harmless `tokenizer`.

Default names: `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, `api-key`,
`api_key`, `access_token`, `refresh_token`, `password`, `secret`, `token`.

Name-based masking replaces the whole value, so a nested message under a field named `token`
disappears entirely rather than being walked into. Traversal stops at 64 levels and replaces what is
left with `<превышена глубина вложенности>` — a recursive structure must not take the call down with it.

## Global defaults

`log_level`, `err_log_level`, `json_indent` and the payload length limit fall back to
`grpc_client.config.LOGGING_CONFIG` whenever they are not passed to `with_structlogger`. Fill that
singleton once at startup:

```python
import logging

from grpc_client import configure_logging

configure_logging(
    log_level=logging.DEBUG,
    err_log_level=logging.WARNING,
    json_indent=2,
    payload_log_maxlength=4096,
)
```

Only `DEBUG`, `INFO`, `WARNING`, `ERROR` and `CRITICAL` are accepted for the two levels, here and in
`configure_logging(...)` alike — a level structlog has no name for raises `ValueError` when the client
is built.

Environment variables **override** the arguments of that function — but only while it runs. Nothing
reads them on import, so a project that never calls `configure_logging(...)` gets library defaults no
matter what the environment says:

| Variable | Field | Used by this library |
|---|---|---|
| `GRPC_CLIENT_LOG_LEVEL` | `log_level` | yes |
| `GRPC_CLIENT_ERR_LOG_LEVEL` | `err_log_level` | yes |
| `GRPC_CLIENT_JSON_INDENT` | `json_indent` | yes |
| `GRPC_CLIENT_PAYLOAD_LOG_MAXLENGTH` | `payload_log_maxlength` | yes — argument `payload_maxlength` |
| `GRPC_CLIENT_USE_LINE_BREAKS` | `use_line_breaks` | no — text-log only setting |

Precedence: argument of `with_structlogger` → env variable → `configure_logging` argument → library
default (the middle two only apply once `configure_logging(...)` has run). `use_line_breaks` is the only setting with no counterpart here — this library never joins
fields into one line.

## Event names

`grpc request sent` and `grpc response received`, exported as `sink.REQUEST_EVENT` and
`sink.RESPONSE_EVENT`. They are not part of the public API (`__init__` exports
`with_structlogger` only) — filter by them in log queries, but do not import them into production code.
