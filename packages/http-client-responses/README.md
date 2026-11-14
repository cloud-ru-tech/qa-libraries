# HTTP client response objects

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-responses)](https://pypi.org/project/cloudru-qa-http-client-responses/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-responses)](https://pypi.org/project/cloudru-qa-http-client-responses/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-responses)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Wrappers around `httpx.Response` that know how to parse the response body.

A client method returns an object typed for the expected data instead of a plain `Response` from which you extract JSON manually. The type is visible in the method signature, parsing takes one line, and your IDE and mypy know the model fields.

- [HTTP client response objects](#http-client-response-objects)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Usage](#usage)
    - [Response attributes](#response-attributes)
    - [Parsing errors](#parsing-errors)
    - [Asynchronous clients](#asynchronous-clients)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-http-client-responses
```

Import the library as the `http_client_responses` module.

## Skills for AI agents

The package includes the [`http-client-responses-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-responses-usage/SKILL.md) skill
with examples and usage rules for AI agents. Install the library
in your project environment, then run this from its root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-responses-usage --yes
```

For Claude Code, add `--claude`. The instructions are shipped with the library version.

## Usage

- `JsonResponse[PydanticModel]` — response body described by a pydantic model. Replace `PydanticModel` with your model.
- `GenericResponse[ReturnType]` — body parsed by a supplied function.
- `ResponseWrapper` — no body parsing, for when you need only status, headers, and content.

```python
from http_client import HttpClient
from httpx import Response
from pydantic import BaseModel
from http_client_responses import GenericResponse, JsonResponse


class ExampleRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    search: str | None = None


class User(BaseModel):
    name: str
    age: int
    alive: bool
    skills: list[str]


class ExampleResponse(BaseModel):
    users: list[User]
    total: int


class ExampleClient(HttpClient):
    """Test HTTP client."""

    def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        """Send a simple GET request for a user list in JSON format."""
        response = self.get(
            url="/users",
            params=request.model_dump(exclude_none=True),
        )
        return JsonResponse(
            response=response,
            schema=ExampleResponse,
        )

    def download_details(self, user_id: int) -> GenericResponse[dict[str, str]]:
        """Send a request for string data to convert into a dict."""
        response = self.get(f"/user/{user_id}/details")

        def parser(r: Response) -> dict[str, str]:
            result = dict()
            for line in r.text.split("\n"):
                key, value = line.split(":", maxsplit=1)
                result[key] = value.strip()
            return result

        return GenericResponse(
            response=response,
            parser=parser,
        )
```

Parse the body explicitly: `model()` for `JsonResponse`, `parse()` for `GenericResponse`.

```python
response = client.get_users(ExampleRequest(limit=10))

assert response.status_code == 200
assert response.model().total == 42
```

`raise_for_status()` returns the wrapper itself, making status checks easy to chain:

```python
users = client.get_users(ExampleRequest()).raise_for_status().model()
```

### Response attributes

| Attribute | Type | Notes |
|---|---|---|
| `status_code` | `int` | |
| `reason_phrase` | `str` | |
| `headers` | `httpx.Headers` | `get_list()` returns all values for a repeated header |
| `raw_headers` | `dict[str, str]` | one value per header |
| `cookies` | `httpx.Cookies` | |
| `content` / `text` | `bytes` / `str` | |
| `url` | `str` | |
| `request` | `httpx.Request` | |
| `elapsed` | `timedelta` | |
| `is_success` / `is_error` | `bool` | |
| `is_client_error` / `is_server_error` | `bool` | 4xx / 5xx |
| `raise_for_status()` | `Self` | raises `httpx.HTTPStatusError` for any non-2xx status |
| `json()` | `Any` | parse the body as JSON without schema validation |

For `Set-Cookie` and other repeated headers, use `headers.get_list("set-cookie")`.

### Parsing errors

If the body cannot be parsed, `ResponseParseError` is raised instead of a plain `pydantic.ValidationError`, showing which request failed and what the server returned:

Library-generated messages retain their original Russian text.

```
ResponseParseError: не удалось разобрать тело ответа
  GET http://test.com/users -> 200
  Body: {"users": [{"name": "John Doe"}], "total": "many"}
  Причина: 1 validation error for ExampleResponse
  total
    Input should be a valid integer, unable to parse string as an integer
```

The original exception is available in `error.cause` and `__cause__`.

### Asynchronous clients

```python
from http_client import AsyncHttpClient


class AsyncExampleClient(AsyncHttpClient):
    async def get_users(self, request: ExampleRequest) -> JsonResponse[ExampleResponse]:
        response = await self.get(url="/users", params=request.model_dump(exclude_none=True))
        return JsonResponse(response=response, schema=ExampleResponse)
```

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                              # install dependencies for all libraries from uv.lock
make test-http-client-responses        # tests for this library
make typecheck-http-client-responses   # mypy for this library
make check                             # formatting, ruff, mypy, and tests for the entire workspace
```

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-http-client-responses PYTHON_VERSION=3.14`.

Publish a release with the git tag `http-client-responses/v<version>`. The tag version must match
the version in `packages/http-client-responses/pyproject.toml`.
