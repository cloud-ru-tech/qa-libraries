# Field catalog and configuration

Two records per HTTP call. Field sets differ; `headers`, `body` and `trace_id` are shared.

## Request — `http request sent`

| Field | Type | Value |
|---|---|---|
| `method` | `str` | uppercase method |
| `url` | `str` | `scheme://host/path` — no query string, it lives in `query_params` |
| `query_params` | `str` | JSON object of the query; **absent** when the URL carries no query |
| `headers` | `str` | JSON object of the headers, after masking |
| `body` | `str` | rendered by `Content-Type`; **absent** when the request has no body |
| `trace_id` | `str` | UUID4 written into `request.extensions["trace_id"]` |

## Response — `http response received`

| Field | Type | Value |
|---|---|---|
| `status_code` | `int` | HTTP status |
| `headers` | `str` | JSON object of the response headers, after masking |
| `body` | `str` | rendered by `Content-Type`; **absent** when the response has no body |
| `trace_id` | `str` | the value taken from the request; `<without trace_id>` if the request never passed the request hook |

`status_code` is the only field that is not a string. Composite values (headers, query, JSON body) are
serialized into JSON strings — see `pitfalls.md` for why that matters to the renderer.

A response is not logged at all when the request fails before a response exists — a connect error or
timeout raises out of `httpx` and only the request record remains. Catch those in the calling code;
the option does not log exceptions.

## Body rendering

The body is chosen by the `Content-Type` header:

| `Content-Type` | `body` holds |
|---|---|
| `application/json` | the parsed, masked, re-serialized body |
| `text/plain` | the text, decoded using the `charset` parameter of the header |
| `application/octet-stream` | the decoded text, or `<binary content (N bytes)>` when it is not text |
| anything else | `<not logged, content-type: application/pdf>` |
| header absent, or empty body | the field is omitted entirely |

So a missing `body` means there was nothing to log; `<not logged, ...>` means there was a body and its
type is not rendered. Only `application/json` is masked — the other types are logged verbatim, so do
not put secrets into a `text/plain` body.

### Truncation

Length limits come from the global `http_client` config and are applied per content type:

| Content type | Limit | Default |
|---|---|---|
| `application/json` | `json_log_maxlength` | unlimited |
| `text/plain` | `plain_text_log_maxlength` | unlimited |
| `application/octet-stream` | `octet_stream_log_maxlength` | 1024 characters |

Truncation cuts the **middle** and inserts `...`, keeping the head and tail — the start of a payload
and its end both stay visible. These limits cannot be set per client, only globally.

### Streaming

| Case | `body` holds |
|---|---|
| response obtained via `stream()` / `stream_request()` and not yet read | `<streamed content>` |
| request with a streaming body (generator, file object) | `<streamed content>` |

Reading either one inside the hook would consume the stream before the caller gets it, so the
placeholder is by design, not a failure. Everything else about the record — status, headers, masking of
those headers — is logged normally.

### Parse errors

Any failure while building a field is caught and replaced with `<Error parse: TypeError>` — the
exception class only. The message is dropped deliberately: it can carry fragments of the body or URL.

Each part is protected independently, so a broken glom path in `sanitize_keys` spoils `headers` while
`body` and the rest stay intact. The request itself never fails because of logging.

## Masking mechanics

Two independent passes run over every value, path-based first, name-based second:

| Mechanism | Source | Matches |
|---|---|---|
| glom paths | `sanitize_keys` | the exact path only — `user.password` does not match `order.user.password` |
| secret names | `DEFAULT_SANITIZE_KEYS` | a field with that name at any depth, including inside arrays |

Both replace the value with `****`. Name matching is case-insensitive; glom paths are literal, and httpx
lowercases header names before the hook runs, so paths that point at headers must be lowercase too.

Default names: `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, `api-key`,
`api_key`, `access_token`, `refresh_token`, `password`, `secret`, `token`.

Name-based masking replaces the whole value, so a nested object under a key named `token` disappears
entirely rather than being walked into.

## Global defaults

`log_level` and `json_indent` fall back to `http_client.config.LOGGING_CONFIG` whenever they are not
passed to `with_structlogger`. Fill that singleton once at startup:

```python
import logging

from http_client import configure_logging
from http_client.config import LoggingConfig

configure_logging(options=LoggingConfig(log_level=logging.DEBUG, json_indent=2, json_log_maxlength=4096))
```

Environment variables **override** the arguments of that function:

| Variable | Field | Used by this library |
|---|---|---|
| `HTTP_CLIENT_LOG_LEVEL` | `log_level` | yes |
| `HTTP_CLIENT_JSON_INDENT` | `json_indent` | yes |
| `HTTP_CLIENT_JSON_LOG_MAXLENGTH` | `json_log_maxlength` | yes |
| `HTTP_CLIENT_PLAIN_TEXT_LOG_MAXLENGTH` | `plain_text_log_maxlength` | yes |
| `HTTP_CLIENT_OCTET_STREAM_LOG_MAXLENGTH` | `octet_stream_log_maxlength` | yes |
| `HTTP_CLIENT_USE_LINE_BREAKS` | `use_line_breaks` | no — text-log only setting |

Precedence for level and indent: argument of `with_structlogger` → env variable → `configure_logging`
argument → library default. `configure_logging` must be called before the client is constructed only
for values you rely on; the hooks read the singleton at call time, so later changes do take effect.

## Event names

`http request sent` and `http response received`, exported as `event_hooks.REQUEST_EVENT` and
`event_hooks.RESPONSE_EVENT`. They are not part of the public API (`__init__` exports `with_structlogger`
only) — filter by them in log queries, but do not import them into production code.
