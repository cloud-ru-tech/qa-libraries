# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## `raise_for_status()` fires on every non-2xx status

The name suggests "errors", but the check is `2xx or raise`. Informational and redirect statuses raise too:

| Status | Result |
|---|---|
| 100, 301, 302, 304 | `httpx.HTTPStatusError` |
| 200, 204 | passes |
| 404, 500 | `httpx.HTTPStatusError` |

This is plain `httpx` behaviour, not something the wrapper adds. A client that does not follow redirects and chains `raise_for_status()` will blow up on a perfectly normal 302. Check `is_success` / `status_code` when you need finer control.

A response built by hand without a request raises `RuntimeError` from `raise_for_status()` — httpx needs the request to build the error message.

## Parsing is deferred, so failures surface at the call site

The constructor stores the response and the parser and does nothing else. `ResponseParseError` is raised by `model()` / `parse()` / `json()`, not by the client method that returned the wrapper. A `try/except` around `client.get_users()` catches nothing.

## The successful result is cached, the failure is not

`parse()` stores the parsed value and returns the same object on every later call — `model() is model()` is `True`, and mutating it is visible to the next caller.

A failed parse is not cached: the parser runs again on the next call and raises again. That matters for a parser with side effects (writing a file, incrementing a counter) — it will run once per attempt.

The sentinel for "not parsed yet" is a private `_UNSET` object, not `None`, because `None` is a valid parse result.

## Streamed bodies are not readable by these wrappers

`JsonResponse` validates from `response.content`. On a response whose body has not been read, `.content` raises `httpx.ResponseNotRead`, which is caught and re-raised as `ResponseParseError` with `Body: <streamed content>` in the message and `ResponseNotRead` in `cause`.

Call `response.read()` (or `await response.aread()`) before wrapping, or work with the raw `httpx` response for streaming endpoints. `elapsed` raises `RuntimeError` for the same reason — httpx only sets it once the body is fully read.

## `raw_headers` collapses repeated headers

```python
wrapper.raw_headers  # {'set-cookie': 'a=1, b=2'}
wrapper.headers.get_list("set-cookie")  # ['a=1', 'b=2']
```

`raw_headers` exists for code that wants a plain `dict` (comparing in a test, dumping to a log). Anything that cares about `Set-Cookie`, `Link`, `Warning`, or `Via` must go through `headers`.

## `Content-Type` is ignored

`JsonResponse` calls `model_validate_json` on the raw bytes and never looks at the header. A JSON body served as `text/plain` parses fine; an HTML error page served as `application/json` fails with `ResponseParseError`. If the content type is part of the contract, assert on it separately.

## `json()` does not validate

`ResponseWrapper.json()` returns `object`. It wraps decode failures in `ResponseParseError` and
performs no schema validation. Narrow the result before using fields, or describe the shape with
a pydantic model and use `JsonResponse`.

## Error messages are in Russian

`ResponseParseError` builds its message from Russian phrases (`"не удалось разобрать тело ответа"`, `"Причина:"`, `"обрезано, всего N байт"`). Do not match error text in English when writing an assertion. The body preview is cut to `ResponseParseError.BODY_PREVIEW_LIMIT` bytes — that constant is public, use it instead of hardcoding 512.

Truncation happens on bytes before decoding, so a multi-byte character split at the boundary becomes `�` rather than raising. That is deliberate: decoding the whole body to trim a few hundred characters would pull a multi-megabyte response into memory.

## Manually built responses degrade instead of failing

`__repr__` prints `?` for method and URL when the response has no request:

```
<ResponseWrapper ? ? -> 204>
```

The same `?` appears inside a `ResponseParseError` message. The properties `url` and `request`, however, raise `RuntimeError` — only the message builders are forgiving. In tests, pass `request=Request("GET", url)` whenever the assertion touches the URL.

## False alarms when reading the code

- The parse cache is typed as `RT | _Unset`; the private sentinel distinguishes an unparsed value
  from a valid parsed `None`. The public `parse()` result remains `RT`.
- `JsonResponse` keeps a `schema` attribute even though the parser closure already captured it — it is there for introspection and debugging.
- `except Exception` in `parse()` and `json()` is intentionally broad: a parser is arbitrary user code and may raise anything. The original exception is preserved in `cause` and `__cause__`, so nothing is swallowed.
- `_utils.py` is private. Its constants (`UNKNOWN`, `STREAMED_BODY`) are implementation detail; assert against `ResponseParseError.BODY_PREVIEW_LIMIT` and the message text instead.
