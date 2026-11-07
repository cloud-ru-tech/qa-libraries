---
name: http-client-responses-usage
description: Typing HTTP client responses with the http_client_responses library — wrappers over httpx.Response that carry the parsed body type, so a client method returns JsonResponse[Model] instead of a bare Response. Use when adding or annotating endpoint methods, validating a response body against a pydantic model, parsing a non-JSON body, or handling body parse failures. Key names are ResponseWrapper, GenericResponse, JsonResponse, ResponseParseError, model(), parse(), raise_for_status().
license: Apache-2.0
metadata:
  library-version: "1.0.0"
  source: packages/http-client-responses
---

# Typing responses with http_client_responses

The library gives an endpoint method a return type that says what the body contains. Instead of `-> httpx.Response` followed by a manual `response.json()` and a hand-written validation, the method returns `JsonResponse[User]` and the caller writes `.model()`.

Three classes, all wrapping a single `httpx.Response`:

| Class | When | How the body is read |
|---|---|---|
| `JsonResponse[Model]` | body is JSON described by a pydantic model | `model()` |
| `GenericResponse[T]` | body needs a custom parser (CSV, plain text, protobuf, XML) | `parse()` |
| `ResponseWrapper` | body is not parsed at all, or only status/headers matter | `json()`, `text`, `content` |

`JsonResponse` is a `GenericResponse`, which is a `ResponseWrapper` — everything below `ResponseWrapper` is available on all three.

The library depends only on `httpx` and `pydantic`. It works with any `httpx.Response`, from `http_client` or from a plain `httpx.Client`.

## Hard rules

1. Annotate the endpoint method with the concrete parameter: `-> JsonResponse[User]`, not `-> JsonResponse`. That annotation is the whole point of the library — without it the caller gets no types.
2. Do not parse inside the endpoint method. The constructor never touches the body; parsing happens when the caller asks for it. A method that returns `User` instead of `JsonResponse[User]` throws away the status, headers, and the ability to assert on a failed response.
3. Catch `ResponseParseError`, never `pydantic.ValidationError`. Every parser failure is wrapped, including the pydantic one.
4. Do not reimplement `raise_for_status`, `is_success`, or header lookup — they are already on the wrapper.
5. For streaming responses, either use the raw `httpx` response or call `read()` before parsing. See `references/pitfalls.md`.

Before claiming a wrapper cannot do something, check `references/pitfalls.md` — it documents the behaviour that trips people up.

## Canonical client (sync)

```python
from http_client import HttpClient
from http_client_responses import GenericResponse, JsonResponse
from httpx import Response
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int
    skills: list[str]


class UsersPage(BaseModel):
    users: list[User]
    total: int


def parse_details(response: Response) -> dict[str, str]:
    """Parse a `key: value` per line body into a dict."""
    result = {}
    for line in response.text.split("\n"):
        key, value = line.split(":", maxsplit=1)
        result[key] = value.strip()
    return result


class UsersClient(HttpClient):
    """Client for the users service."""

    def get_users(self, limit: int = 100, offset: int = 0) -> JsonResponse[UsersPage]:
        response = self.get("/users", params={"limit": limit, "offset": offset})
        return JsonResponse(response=response, schema=UsersPage)

    def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        response = self.get(f"/user/{user_id}/details")
        return GenericResponse(response=response, parser=parse_details)
```

`schema` fixes the type parameter of `JsonResponse`; the parser's return type fixes the type parameter of `GenericResponse`. Both are inferred, so the explicit `-> JsonResponse[UsersPage]` on the method is for the reader, not for mypy.

Keep the parser a named module-level function rather than a `lambda` in the call. A `lambda` types fine, but it cannot be unit-tested on its own or shared between the sync and async client.

## Canonical client (async)

Only the base class and `await` change. The wrappers are the same objects — they hold an already-received response, so there is nothing async about them.

```python
from http_client import AsyncHttpClient


class AsyncUsersClient(AsyncHttpClient):
    async def get_users(self, limit: int = 100) -> JsonResponse[UsersPage]:
        response = await self.get("/users", params={"limit": limit})
        return JsonResponse(response=response, schema=UsersPage)
```

`model()` and `parse()` stay synchronous. Never `await` them.

## Reading the response

```python
response = client.get_users(limit=10)

assert response.status_code == 200
assert response.model().total == 42
```

`raise_for_status()` returns the wrapper itself, so a status check chains:

```python
page = client.get_users().raise_for_status().model()
```

The parsed value is computed once and reused, so calling `model()` in several assertions costs one validation:

```python
page = response.model()
assert page.total == 42
assert page.users[0].name == "John Doe"  # same object, no re-validation
```

## Response attributes

Available on `ResponseWrapper`, and therefore on all three classes.

| Attribute | Type | Note |
|---|---|---|
| `status_code` | `int` | |
| `reason_phrase` | `str` | |
| `headers` | `httpx.Headers` | case-insensitive; `get_list()` returns every value of a repeated header |
| `raw_headers` | `dict[str, str]` | one value per header, repeats joined by `, ` |
| `cookies` | `httpx.Cookies` | |
| `content` / `text` | `bytes` / `str` | |
| `url` | `str` | |
| `request` | `httpx.Request` | |
| `elapsed` | `timedelta` | |
| `is_success` / `is_error` | `bool` | |
| `is_client_error` / `is_server_error` | `bool` | 4xx / 5xx |
| `raise_for_status()` | `Self` | raises `httpx.HTTPStatusError` on **any** non-2xx status |
| `json()` | `object` | JSON parse without schema validation; narrow or validate before accessing fields |
| `response` | `httpx.Response` | the wrapped response, for anything the facade does not cover |

Use `headers.get_list("set-cookie")` for headers a server sends more than once — `raw_headers` collapses them into one string.

## Parse errors

Any exception raised while reading the body is wrapped in `ResponseParseError`, which adds the HTTP context to the message:

```
ResponseParseError: не удалось разобрать тело ответа
  GET http://test.com/users -> 200
  Body: {"users": [{"name": "John Doe"}], "total": "много"}
  Причина: 1 validation error for UsersPage
  total
    Input should be a valid integer, unable to parse string as an integer
```

```python
from http_client_responses import ResponseParseError

try:
    page = client.get_users().model()
except ResponseParseError as error:
    log.warning("bad body from users service: %s", error)
    raise
```

- `error.cause` and `error.__cause__` hold the original exception (`pydantic.ValidationError`, `json.JSONDecodeError`, whatever the parser raised).
- `error.response` holds the `httpx.Response`.
- The body in the message is truncated to `ResponseParseError.BODY_PREVIEW_LIMIT` bytes (512).

`raise_for_status()` does not raise this — a 500 with a valid body is not a parse error. Check the status and parse the body as two separate steps.

## Testing with these wrappers

The wrapper takes any `httpx.Response`, so a unit test does not need a client:

```python
from httpx import Request, Response

wrapper = JsonResponse(Response(200, json={"users": [], "total": 0}), UsersPage)
assert wrapper.model().total == 0
```

Pass `request=Request("GET", url)` whenever the test touches `url`, `request`, `raise_for_status()`, or `repr()` — a response built without one raises `RuntimeError` on those. See `references/pitfalls.md`.

## Known pitfalls

Read `references/pitfalls.md` before debugging odd behaviour. It covers non-2xx statuses in `raise_for_status`, streamed bodies, what is and is not cached, header collapsing, and manually built responses.
