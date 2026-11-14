# Structured logs for the gRPC client

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-grpc-client-structlog)](https://pypi.org/project/cloudru-qa-grpc-client-structlog/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-grpc-client-structlog)](https://pypi.org/project/cloudru-qa-grpc-client-structlog/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-grpc-client-structlog)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

The `with_structlogger` option for the [gRPC client](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client)
logs all requests and responses through [structlog](https://www.structlog.org/en/stable/index.html).

The standard grpc-client logger puts the request in one text string. This option logs the method, body,
metadata, and status as separate fields, visible in the console during debugging and available
for searching and filtering in collected logs.

- [Installation](#installation)
- [Skills for AI agents](#skills-for-ai-agents)
- [Usage](#usage)
- [Asynchronous client](#asynchronous-client)
- [Log fields](#log-fields)
- [Masking secrets](#masking-secrets)
- [Parameters](#parameters)
- [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-grpc-client-structlog
```

Import the library as `grpc_client_structlog`. A compatible version of
[`cloudru-qa-grpc-client`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client)
is installed with it.

## Skills for AI agents

The package includes the [`grpc-client-structlog-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/grpc-client-structlog-usage/SKILL.md) skill
with examples and usage rules for AI agents. Install the library
in your project environment, then run this from its root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill grpc-client-structlog-usage --yes
```

For Claude Code, add `--claude`. The instructions are shipped with the library version.

## Usage

Pass the option to the client constructor; logging is then automatic:

```python
import structlog

from grpc_client import GRPCClient
from grpc_client_structlog import with_structlogger

from api import orders_pb2, orders_pb2_grpc


class OrdersClient(GRPCClient[orders_pb2_grpc.OrdersStub]):
    @property
    def stub_class(self):
        return orders_pb2_grpc.OrdersStub

    def get_order(self, order_id: str):
        return self.send_unary_unary_request(orders_pb2.GetOrderRequest(id=order_id), self.stub.GetOrder)


with OrdersClient.from_addr(
    "orders.example.com:443",
    with_structlogger(structlog.get_logger("orders")),
) as client:
    client.get_order("42")
```

The request is logged as a `grpc request sent` event, the response as `grpc response received`.
A shared `trace_id` field links them.

## Asynchronous client

Use the same option without extra configuration: the interceptor is selected
based on the client type:

```python
from grpc_client import AsyncGRPCClient


class AsyncOrdersClient(AsyncGRPCClient[orders_pb2_grpc.OrdersStub]):
    @property
    def stub_class(self):
        return orders_pb2_grpc.OrdersStub

    async def get_order(self, order_id: str):
        return await self.send_unary_unary_request(orders_pb2.GetOrderRequest(id=order_id), self.stub.GetOrder)


async with AsyncOrdersClient.from_addr("orders.example.com:443", with_structlogger(logger)) as client:
    await client.get_order("42")
```

The final response-stream record is written in a separate task, so close the asynchronous
client: `close()` waits for these tasks.

## Log fields

Up to two records per call, linked by a shared `trace_id`: request and response.

| Field | Event | Value |
|---|---|---|
| `method` | both | full method name such as `/package.Service/Method` |
| `body` | both | message body as a JSON string; responses include it only for successful unary calls |
| `metadata` | both | metadata as a JSON string; omitted if no metadata was present |
| `status_code` | response | status code name: `OK`, `NOT_FOUND`, … |
| `details` | response | service error text; present only for failed calls |
| `messages_count` | response | number of messages received from the stream; present only for streaming calls |
| `trace_id` | both | UUID4 generated per request |

`status_code` contains the code **name**, not its number. Names are readable without a reference
and easy to filter. Including the number would give the field two values and require
substring searches for `5 (NOT_FOUND)`.

Compound values, `body` and `metadata`, are serialized as JSON strings before logging,
rather than nested structures, to avoid mixing their fields with application context fields.

Neither request nor response stream bodies are logged: consuming a stream for logging would change
call behavior. A streaming request uses `<streamed content>` in `body`, while a response stream
logs its final status and `messages_count`.

Long bodies are truncated at 4096 characters by default, followed by
`... <обрезано>` in `body`. Set the limit with `payload_maxlength`. If preparing the body fails,
for example because of an invalid glom path in `sanitize_keys`, `body` contains
`<не удалось подготовить тело сообщения>`. The request still goes through: logging is designed
to avoid breaking calls.

## Masking secrets

Fields with common secret names are masked **by default at every depth**, including
nested messages and array items:

`authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, `api-key`, `api_key`,
`access_token`, `refresh_token`, `password`, `secret`, `token`.

Names match across naming styles, so `accessToken` in a message body is also hidden.

Add your own fields with `sanitize_keys`. A key without separators is treated as a field name
and masked at every depth; a key with a dot, star, or brackets is treated as a path
[glom](https://glom.readthedocs.io/en/latest/):

```python
with_structlogger(
    logger,
    sanitize_keys=["x-tenant-key", "user.internal_id", "items.*.card_number"],
)
```

Disable the default list explicitly with `use_default_sanitize_keys=False`.

Masking leaves the original message unchanged: `****` appears only in the log.

The `details` field, containing service error text, is neither masked nor truncated: it is free text,
while masking works with field names and paths. If the service puts confidential information
in the status, it appears in the log unchanged. The standard `options.with_logger` behaves the same way.

## Parameters

| Parameter | Type | Purpose |
|---|---|---|
| `logger` | `BoundLogger \| FilteringBoundLogger` | where to write |
| `sanitize_keys` | `Sequence[str] \| None` | field names and glom paths whose values are replaced with `****` |
| `json_indent` | `int \| None` | indentation width for JSON properties |
| `log_level` | `int \| None` | level for successful records; `INFO` by default |
| `err_log_level` | `int \| None` | level for failed calls; `ERROR` by default |
| `payload_maxlength` | `int \| None` | maximum logged body length; 4096 characters by default |
| `use_default_sanitize_keys` | `bool` | mask common secrets at every depth; `True` by default |

Set levels, indentation, and body length limits for the whole project with
`grpc_client.configure_logging(...)`. Values passed to `with_structlogger` override shared settings.

`GRPC_CLIENT_*` environment variables have no effect on their own: `configure_logging(...)` reads them
when called. Without that call, the library defaults remain in effect.

`log_level` and `err_log_level` accept only `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`:
structlog's bound logger selects a method by level name, and only these five names are available.
An intermediate value such as `15` raises `ValueError` immediately, rather than on the first request.

structlog filters levels itself: if the logger threshold is above `log_level`, the record does not
reach the output and the option may appear broken.

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                               # install dependencies for all libraries from uv.lock
make test-grpc-client-structlog         # tests for this library
make typecheck-grpc-client-structlog    # mypy for this library
make check                              # formatting, ruff, mypy, and tests for the entire workspace
```

Tests require Docker running: the gRPC service starts in a container from `tests/docker-compose.yml`,
and its image is built on the first run. If the service is already running, skip starting the container
by passing its address:

```shell
uv run --no-sync python packages/grpc-client-structlog/tests/service.py &
SERVICE_ADDR=localhost:50051 make test-grpc-client-structlog
```

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-grpc-client-structlog PYTHON_VERSION=3.14`.

Publish a release with the git tag `grpc-client-structlog/v<version>`. The tag version must match
the version in `packages/grpc-client-structlog/pyproject.toml`.
