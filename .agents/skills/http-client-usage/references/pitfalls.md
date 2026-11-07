# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## Options run before the httpx client exists

Order inside `__init__`: `BaseHttpClient.__init__` creates typed internal configuration and runs
the options; then `HttpClient.__init__` creates the httpx transport from that configuration.

Two consequences:

1. An option that touches `client.client` raises `AttributeError` — there is no transport yet.
2. Setting `client.timeout`, `auth`, `verify` or `url_suffix` after construction raises `RuntimeError`.
   Set them through constructor options. For transport-level changes supported by httpx, use its
   public API directly, for example `client.client.timeout`, or rebuild the client.

## Decorators are frozen once

Decorators are composed in `__init__`. Register them through constructor options with
`add_send_decorator` / `add_stream_decorator` or the built-in option factories. Late registration
raises `RuntimeError`.

Composition order is a plain loop:

```python
for decorator in decorators:
    func = decorator(func)
```

so the last decorator added ends up outermost and runs first.

## `endpoint()` only accepts relative paths

An absolute URL or a `..` segment raises `ValueError` instead of silently escaping the client's base URL. Build cross-host calls with a separate client, not by passing a full URL to `endpoint()`.

## A decorator that sends twice runs the hooks twice

Event hooks fire inside `httpx.Client.send`, so a decorator that calls `func()` twice runs every
request hook twice. The built-in ID hooks preserve existing `X-Request-ID` and `Traceparent` values;
reusing one request keeps its identifiers stable across retries. A newly built request gets new
identifiers unless the caller provided them. Other hooks, including logging, still run per attempt.

## Streaming: the logged response body is always a placeholder

`stream_request` marks the request with `request.extensions["is_streaming"] = True`. The logging response hook sees the marker and, while the body is unread, writes `Body: <streamed content>`. This is by design — reading the body inside the hook would defeat the purpose of streaming.

## `HttpClient` and `AsyncHttpClient` are declared abstract yet instantiable

Both carry `metaclass=ABCMeta`, but the only abstract member, `BaseHttpClient.client`, is implemented in each. So `HttpClient("https://...")` works — the library's own tests rely on it. Subclassing is still the preferred approach, but direct construction is not a mistake.

## False alarms when reading the code

- `logutils.create_request_log` writes `r.extensions["trace_id"]`, meaning the logging hook mutates the request. Keep that in mind when comparing `extensions` in tests.
