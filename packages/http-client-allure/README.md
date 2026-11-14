# Options for integrating the HTTP client with Allure

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-http-client-allure)](https://pypi.org/project/cloudru-qa-http-client-allure/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-http-client-allure)](https://pypi.org/project/cloudru-qa-http-client-allure/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-http-client-allure)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

The library adds options to the [HTTP client](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/http-client) that wrap each request in a separate Allure step and attach request and response data.

Use it to see which requests were sent, their bodies, and service responses in automated test reports, without manual `allure.step` and `allure.attach` calls in tests.

- [Options for integrating the HTTP client with Allure](#options-for-integrating-the-http-client-with-allure)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Quick start](#quick-start)
  - [Options](#options)
    - [`wrap_requests_in_steps`](#wrap_requests_in_steps)
    - [`wrap_requests_and_responses_in_steps`](#wrap_requests_and_responses_in_steps)
  - [Parameters](#parameters)
  - [Response headers](#response-headers)
  - [Masking secrets](#masking-secrets)
  - [Requests as curl commands](#requests-as-curl-commands)
  - [Asynchronous client](#asynchronous-client)
  - [Streaming requests](#streaming-requests)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-http-client-allure
```

Import the library as the `http_client_allure` module.

## Skills for AI agents

The package includes the [`http-client-allure-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/http-client-allure-usage/SKILL.md) skill
with examples and usage rules for AI agents. Install the library
in your project environment, then run this from its root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill http-client-allure-usage --yes
```

For Claude Code, add `--claude`. The instructions are shipped with the library version.

## Quick start

Pass the option to the client constructor: all requests then appear in the report automatically:

```python
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

client = HttpClient(
    "https://example.com",
    wrap_requests_and_responses_in_steps(),
)

client.get("/sample")
```

## Options

### `wrap_requests_in_steps`

Wraps each request in an Allure step and attaches the request data.

![simpla_request](https://raw.githubusercontent.com/cloud-ru-tech/qa-libraries/master/packages/http-client-allure/assets/simple_request.png)

```python
from http_client import HttpClient
from http_client_allure import wrap_requests_in_steps

client = HttpClient("https://example.com", wrap_requests_in_steps())
```

The step shows the request duration. If the service does not respond because of a lost connection or timeout, the step still appears in the report and is marked as failed.

### `wrap_requests_and_responses_in_steps`

The same, but also attaches response data to the step.

![json_response](https://raw.githubusercontent.com/cloud-ru-tech/qa-libraries/master/packages/http-client-allure/assets/json_response.png)

```python
from http_client import HttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

client = HttpClient("https://example.com", wrap_requests_and_responses_in_steps())
```

## Parameters

Both options accept the same parameters.

| Parameter | Default | Behavior |
|---|---|---|
| `show_host` | `False` | show the request host in the step title |
| `show_query_params` | `False` | show query parameters in the step title |
| `attach_request` | `True` | attach request data to the step |
| `attach_response` | `True` | attach the response body (only with `wrap_requests_and_responses_in_steps`) |
| `attach_response_headers` | `True` | attach response headers (only with `wrap_requests_and_responses_in_steps`) |
| `serialize_request_to_curl` | `False` | attach the request as a curl command instead of JSON |
| `sanitize_keys` | `None` | keys in [glom](https://glom.readthedocs.io/en/latest/) format whose values should be hidden |
| `use_default_sanitize_keys` | `True` | extend `sanitize_keys` with the secret list from `http_client` |
| `json_dumps_kwargs` | `None` | [`json.dumps`](https://docs.python.org/3/library/json.html#json.dump) parameters for JSON display |
| `max_attach_length` | `None` | maximum attachment length in characters; longer attachments are truncated |

## Response headers

Response headers and body are attached to the step separately:

- `Response headers: status = 200 [OK]` — response headers with secrets masked,
- `Response content` — response body.

The separate header attachment is visible even without a body, such as for `204 No Content`, and for streaming responses whose bodies are not included in the report.

Attachments are independent, so you can keep only the headers:

```python
wrap_requests_and_responses_in_steps(attach_response=False)
```

The response status appears only in the header attachment's name. Disabling it with `attach_response_headers=False` removes the status from the report: the step title is built before sending the request, so the status is not yet known.

## Masking secrets

Secrets in headers, query parameters, and bodies are hidden automatically: `authorization`, `cookie`, `x-api-key`, `token`, `password`, and other common keys.

Add your own keys:

```python
wrap_requests_in_steps(sanitize_keys=["data.password", "items.*.token"])
```

Keep only your own keys without the defaults:

```python
wrap_requests_in_steps(sanitize_keys=["data.password"], use_default_sanitize_keys=False)
```

## Requests as curl commands

To copy a request from the report and rerun it in a terminal:

```python
wrap_requests_in_steps(serialize_request_to_curl=True)
```

![curl_request](https://raw.githubusercontent.com/cloud-ru-tech/qa-libraries/master/packages/http-client-allure/assets/curl_request.png)

## Asynchronous client

Both options also work with `AsyncHttpClient` and are configured the same way:

```python
from http_client import AsyncHttpClient
from http_client_allure import wrap_requests_and_responses_in_steps

async with AsyncHttpClient("https://example.com", wrap_requests_and_responses_in_steps()) as client:
    await client.get("/sample")
```

Concurrent requests through `asyncio.gather` are supported: each gets its own step and data. Unlike synchronous steps, asynchronous steps do not show request duration.

## Streaming requests

`client.stream(...)`, `client.stream_request(...)`, and `client.send(request, stream=True)` also appear in the report.

The stream body is not included in the report; it uses the `<streamed content>` placeholder. If you read the body yourself inside the step, the report includes it.

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                            # install dependencies for all libraries from uv.lock
make test-http-client-allure         # tests for this library
make typecheck-http-client-allure    # mypy for this library
make check                           # formatting, ruff, mypy, and tests for the entire workspace
```

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-http-client-allure PYTHON_VERSION=3.14`.

A demo project with real requests and a generated Allure report is in `examples/`.

Publish a release with the git tag `http-client-allure/v<version>`. The tag version must match
the version in `packages/http-client-allure/pyproject.toml`.
