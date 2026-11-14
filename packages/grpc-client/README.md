# Base gRPC client

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-grpc-client)](https://pypi.org/project/cloudru-qa-grpc-client/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-grpc-client)](https://pypi.org/project/cloudru-qa-grpc-client/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-grpc-client)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

Base client for sending requests to gRPC services from automated tests.

- [Base gRPC client](#base-grpc-client)
  - [Installation](#installation)
  - [Skills for AI agents](#skills-for-ai-agents)
  - [Usage](#usage)
    - [1. Generate code from proto](#1-generate-code-from-proto)
    - [2. Write your own client](#2-write-your-own-client)
    - [3. Create a client and set options](#3-create-a-client-and-set-options)
    - [4. Call methods](#4-call-methods)
    - [5. Work with responses](#5-work-with-responses)
    - [6. Streams](#6-streams)
    - [7. Call options](#7-call-options)
    - [8. Metadata](#8-metadata)
    - [9. Errors and rich status](#9-errors-and-rich-status)
    - [10. Authorization](#10-authorization)
    - [11. Logging](#11-logging)
    - [12. Asynchronous client](#12-asynchronous-client)
    - [13. Custom interceptors](#13-custom-interceptors)
  - [Development](#development)

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-grpc-client
```

Import the library as the `grpc_client` module.

If you also need code generation from proto files, install the library with the `codegen` extra:

```shell
pip install "cloudru-qa-grpc-client[codegen]"
```

## Skills for AI agents

The package includes the [`grpc-client-usage`](https://github.com/cloud-ru-tech/qa-libraries/blob/master/.agents/skills/grpc-client-usage/SKILL.md) skill
with examples and usage rules for AI agents. Install the library
in your project environment, then run this from its root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills install --skill grpc-client-usage --yes
```

For Claude Code, add `--claude`. The instructions are shipped with the library version.

## Usage

### 1. Generate code from proto

First, get access to the proto files describing the service contract for your gRPC client. Ask the service developers for them. See the [proto](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client/proto/) directory in this repository for examples.

Once you have access, generate `pb2.py` files from them. Ask whether the developers have already generated these files and published them in a library or repository.

If you need to generate the contract code yourself, copy the proto files into your project (consider [git submodules](https://git-scm.com/book/ru/v2/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D1%8B-Git-%D0%9F%D0%BE%D0%B4%D0%BC%D0%BE%D0%B4%D1%83%D0%BB%D0%B8)). Then use [`protoc`](https://grpc.io/docs/languages/python/quickstart/) from `grpcio-tools`, installed with the `cloudru-qa-grpc-client[codegen]` extra.

ℹ️ See [gen-test-api.sh](https://github.com/cloud-ru-tech/qa-libraries/blob/master/packages/grpc-client/gen-test-api.sh) for a simple example that generates `pb2.py` files for tests.

### 2. Write your own client

The library provides base methods for sending gRPC requests. To use them, create your own client class that inherits from `GRPCClient`, with the service Stub class as its type parameter:

```python
from typing import Type

from grpc_client import CallOptions, GRPCClient, GRPCResponse, MetadataType

# Import the pb2.py modules generated in the previous step
from api import example_pb2, example_pb2_grpc


class MyCustomClient(GRPCClient[example_pb2_grpc.ExampleStub]):
    """gRPC client for the Example service."""

    @property
    def stub_class(self) -> Type[example_pb2_grpc.ExampleStub]:
        return example_pb2_grpc.ExampleStub

    def send_example_request(
        self,
        data: example_pb2.RequestMessage,
        metadata: MetadataType | None = None,
        options: CallOptions | None = None,
    ) -> GRPCResponse[example_pb2.ResponseMessage]:
        """Send a test gRPC request to the service.

        :param data: request data
        :param metadata: request metadata (similar to HTTP headers)
        :param options: call options
        :return: response object containing the response data
        """
        return self.send_unary_unary_request(
            msg=data,
            method=self.stub.ExampleMethod,
            metadata=metadata,
            options=options,
        )
```

In detail:

1. Inherit from `GRPCClient` and specify the Stub class in square brackets to type `self.stub`.
2. Return the same Stub class from the __required__ `stub_class` property. Import it from the generated `pb2_grpc.py` modules; it is named "{service name}Stub". All service methods are then available through `self.stub`.
3. Call a specific request with one of the base class's four sending methods (described below), passing the request data and a method from `self.stub`.

### 3. Create a client and set options

Create a client with the `from_addr` factory method, passing the service address and options:

```python
import logging

from grpc_client import options

client = MyCustomClient.from_addr(
    "localhost:9000",
    options.with_insecure_channel(),
    options.with_timeout(30),
    options.with_logger(logging.getLogger("example")),
    options.with_autogenerated_request_id(),
)

response = client.send_example_request(...)
client.close()
```

⚠️ Close the channel created by the client. The simplest way is to use the client as a context manager:

```python
with MyCustomClient.from_addr("localhost:9000", options.with_insecure_channel()) as client:
    response = client.send_example_request(...)
```

A fixture works well for this in pytest:

```python
@pytest.fixture
def example_client() -> Iterator[MyCustomClient]:
    with MyCustomClient.from_addr("localhost:9000", options.with_insecure_channel()) as client:
        yield client
```

If a channel already exists and the caller manages its lifetime, use `from_channel`: the client does not close that channel:

```python
with grpc.insecure_channel("localhost:9000") as channel:
    client = MyCustomClient.from_channel(channel)
```

Available options:

| Option | Purpose |
| --- | --- |
| `with_timeout(timeout)` | Default call timeout; `None` means no limit |
| `with_insecure_channel()` | Unencrypted channel (channels are encrypted by default) |
| `with_ssl_credentials(credentials)` | Custom TLS credentials |
| `with_root_certificates(pem_bytes)` | Root certificate for verifying the server |
| `with_channel_options(options)` | Low-level grpcio channel settings, including `grpc.service_config` |
| `with_compression(compression)` | Message compression |
| `with_default_metadata(metadata)` | Metadata added to every request |
| `with_auth(auth)` | Add an access token; see [Authorization](#10-authorization) |
| `with_logger(logger, ...)` | Log requests and responses |
| `with_autogenerated_request_id(key)` | Automatic `x-request-id` |
| `with_autogenerated_traceparent(key)` | Automatic `traceparent` following W3C Trace Context |
| `with_interceptor(*interceptors)` | Custom grpcio interceptors |

Option order matters: interceptors run in the order they are added. Add logging after authorization so the log captures the final request.

### 4. Call methods

gRPC has four method types:

1. **Unary** — a regular blocking request: the client sends one message and receives one response.
2. **Client streaming** — the client sends a sequence of messages, then waits for a single response.
3. **Server streaming** — the client sends a request and reads a sequence of response messages.
4. **Bidirectional streaming** — both the client and server send sequences of messages independently.

See the [grpc.io documentation](https://grpc.io/docs/what-is-grpc/core-concepts/) for details.

The base class implements all four:

| Method | Call type | Returns |
| --- | --- | --- |
| `send_unary_unary_request` | unary | `GRPCResponse[T]` |
| `send_stream_unary_request` | client streaming | `GRPCResponse[T]` |
| `send_unary_stream_request` | server streaming | `GRPCStreamResponse[T]` |
| `send_stream_stream_request` | bidirectional streaming | `GRPCStreamResponse[T]` |

ℹ️ In Python, request streams use an [iterator](https://docs.python.org/3/library/stdtypes.html#iterator-types), `Iterator[Message]`. Use `iter` to create a simple iterator from a list.

### 5. Work with responses

Unary methods return `GRPCResponse`:

```python
response = client.send_example_request(data)

response.status_code  # grpc.StatusCode — response status code
response.details  # str — status explanation, usually set for errors
response.ok  # bool — whether the request succeeded
response.message()  # response message; raises MessageUndefinedError if absent
response.initial_metadata  # metadata before the response body, similar to HTTP headers
response.trailing_metadata  # metadata after the response body
response.error  # original grpc.RpcError if the request failed
response.error_status  # rich google.rpc.Status if provided by the service
response.raise_for_status()  # raise ResponseStatusError if status is not OK
```

The client does not raise gRPC errors: each failed call becomes a `GRPCResponse` with the appropriate code. This is useful in automated tests, where a failed response can also be an expected result:

```python
response = client.send_example_request(data)

assert response.status_code == grpc.StatusCode.NOT_FOUND
assert response.details == "order not found"
```

To turn an error into an exception, use `raise_for_status()`.

Use `with_parser` to transform the response message, for example into a pydantic model or a single property:

```python
from pydantic import BaseModel

from grpc_client import GRPCClient, GRPCResponseWithParser, MetadataType

from api import example_pb2, example_pb2_grpc


class ResponseModel(BaseModel):
    prop1: str
    prop2: int
    prop3: bool


class MyCustomClient(GRPCClient[example_pb2_grpc.ExampleStub]):
    @property
    def stub_class(self) -> type[example_pb2_grpc.ExampleStub]:
        return example_pb2_grpc.ExampleStub

    def send_example_request(
        self,
        data: example_pb2.RequestMessage,
        metadata: MetadataType | None = None,
    ) -> GRPCResponseWithParser[example_pb2.ResponseMessage, ResponseModel]:
        """Send a test gRPC request to the service.

        :param data: request data
        :param metadata: request metadata (similar to HTTP headers)
        :return: response object with a response message parser
        """
        response = self.send_unary_unary_request(
            msg=data,
            method=self.stub.ExampleMethod,
            metadata=metadata,
        )

        def parser(msg: example_pb2.ResponseMessage) -> ResponseModel:
            return ResponseModel(
                prop1=msg.prop1,
                prop2=msg.prop2,
                prop3=msg.prop3,
            )

        return response.with_parser(parser)
```

Call `parse()` to get the parsed message.

### 6. Streams

`send_unary_stream_request` and `send_stream_stream_request` return `GRPCStreamResponse`. Messages are read lazily as they arrive, without buffering.

If you need all messages at once, call `collect()`: it consumes the remaining stream and returns a regular `GRPCResponse` with a message list and the final status.

```python
response = client.send_server_stream(data).collect()

assert response.status_code == grpc.StatusCode.OK
for message in response.message():
    ...
```

Lazy reading is useful for long or endless streams:

```python
with client.send_server_stream(data) as stream:
    for message in stream:
        if message.is_last:
            break
```

⚠️ A stream keeps the call open, so consume it fully or close it. The context manager cancels an unfinished call on exit. You can also cancel it explicitly with `cancel()`.

The server provides the final status and trailing metadata only when the stream ends. Accessing them before reading finishes raises `StreamNotConsumedError`:

```python
stream = client.send_server_stream(data)
messages = list(stream)

stream.status_code  # available only now
stream.trailing_metadata
```

Pass `limit` to restrict the number of messages: the call is canceled when the limit is reached:

```python
response = client.send_server_stream(data).collect(limit=100)
```

ℹ️ A stream can be read once: reading it again raises `StreamConsumedError`. If you need the messages again, save them with `collect()`.

### 7. Call options

Client settings apply to all requests. Use `CallOptions` to configure one call:

```python
from grpc_client import CallOptions

response = client.send_example_request(
    data,
    options=CallOptions(
        timeout=120,  # custom timeout for a long-running method
        metadata={"x-attempt": "2"},
        wait_for_ready=True,  # wait for the channel instead of failing with UNAVAILABLE
        compression=grpc.Compression.Gzip,
    ),
)
```

`timeout=None` means no time limit. An omitted `timeout` uses the client settings: these are different behaviors.

### 8. Metadata

Pass metadata as a dictionary or a sequence of pairs; use pairs when a key has multiple values:

```python
client.send_example_request(data, metadata={"x-order-id": "A-1024"})
client.send_example_request(data, metadata=[("x-feature", "search"), ("x-feature", "ranking")])
```

Response metadata is returned as a `Metadata` object. It acts like a dictionary but preserves order and duplicate keys, and compares key names without case sensitivity:

```python
response.trailing_metadata["x-request-id"]  # first value for the key
response.trailing_metadata.get_all("x-feature")  # all values for the key
response.trailing_metadata.pairs()  # all pairs, including duplicate keys
```

ℹ️ Binary values are allowed only for keys ending in `-bin`, as required by gRPC.

### 9. Errors and rich status

Services often send error details in `google.rpc.Status`. The library parses them and exposes them through `error_status`:

```python
response = client.send_example_request(data)

if response.error_status:
    print(response.error_status.code)  # numeric google.rpc.Code
    print(response.error_status.message)  # error text
    print(response.error_status.details)  # typed details

    # look up details by message type
    bad_request = response.error_status.of_type(error_details_pb2.BadRequest)
```

Detail types unknown to the library remain as `google.protobuf.Any`.

Library exceptions inherit from `GRPCClientError`:

| Exception | Raised when |
| --- | --- |
| `MessageUndefinedError` | calling `message()` on a response without a message |
| `ResponseStatusError` | calling `raise_for_status()` with a non-OK status |
| `StreamConsumedError` | reading an already consumed stream again |
| `StreamNotConsumedError` | accessing the final status before consuming the stream |

### 10. Authorization

The library does not determine where tokens come from; it defines the `ClientAuth` contract:

```python
class ClientAuth(Protocol):
    def token(self) -> str: ...
    def refresh(self, rejected_token: str) -> str: ...
```

The rejected token is passed to `refresh()`, allowing the implementation to distinguish an expired token
from one already refreshed by another request while this request waited for a lock, avoiding unnecessary external calls.

The implementation issues tokens, calls the external service, caches tokens, and manages their lifetime. The client adds the header and retries requests:

```python
client = MyCustomClient.from_addr(
    "example.com:443",
    options.with_auth(my_auth),
)
```

The client:

- adds the `authorization: Bearer <token>` header to every request;
- requests a new token with `refresh(rejected_token)` after an `UNAUTHENTICATED` response and retries the unary request;
- leaves authorization unchanged if the caller supplies an `authorization` header.

⚠️ Only unary requests are retried: a request stream is exhausted after the first send, and a response stream's final status is known only after consumption. Disable retries with `options.with_auth(my_auth, retry_on_unauthenticated=False)`.

ℹ️ Ready-to-use IAM authorization is provided by [`cloudru-qa-grpc-client-auth`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client-auth).

### 11. Logging

```python
import logging

client = MyCustomClient.from_addr(
    "example.com:443",
    options.with_logger(
        logging.getLogger("example"),
        sanitize_keys=["user.password"],
        json_indent=2,
    ),
)
```

All four call types are logged. For streams, the log includes the final status and message count, but not the messages: consuming them for logging would change call behavior.

ℹ️ The asynchronous client counts messages received through `async for` and `collect()`; it provides no other stream reading methods.

Secrets are masked:

- in metadata, by case-insensitive key name;
- in message bodies, in two ways depending on the key format:
  - a name without separators (`password`) masks that field at any nesting level, including list items;
  - a path with a dot, star, or brackets (`user.password`, `items.*.token`) is applied as a [glom path](https://glom.readthedocs.io/en/latest/).

Field names match across naming styles, so `access_token` also hides `accessToken` (protobuf serializes fields in camelCase), but does not affect fields with different word boundaries such as `sec_ret`.

Common keys (`authorization`, `cookie`, `password`, `token`, and others) are always masked in metadata and nested body fields. Disable this with `use_default_sanitize_keys=False`.

Set shared logging settings through `configure_logging`; environment variables can override them:

```python
from grpc_client import configure_logging

configure_logging(
    log_level=logging.INFO,
    json_indent=2,
    payload_log_maxlength=4096,
)
```

| Environment variable | Controls |
| --- | --- |
| `GRPC_CLIENT_LOG_LEVEL` | log level for successful requests |
| `GRPC_CLIENT_ERR_LOG_LEVEL` | log level for failed requests |
| `GRPC_CLIENT_JSON_INDENT` | JSON formatting indentation |
| `GRPC_CLIENT_USE_LINE_BREAKS` | whether log properties appear on separate lines |
| `GRPC_CLIENT_PAYLOAD_LOG_MAXLENGTH` | maximum message body length in logs |

#### Custom log format

`with_logger` writes each call as a single string. For another format, such as separate fields in a structured logger, pass a log sink instead of a logger:

```python
from grpc_client import LogSink, RequestRecord, ResponseRecord, options


class MySink(LogSink):
    def is_enabled_for(self, level: int) -> bool:
        return True

    def write_request(self, level: int, record: RequestRecord) -> None: ...

    def write_response(self, level: int, record: ResponseRecord) -> None: ...


client = MyCustomClient.from_addr("example.com:443", options.with_log_sink(MySink()))
```

`LogSink` is a `Protocol`, so inheritance is optional, but inheriting lets mypy check method signatures.

The client builds records and selects the level: `log_level` for successful calls, `err_log_level` for failures. The sink only decides where and how to write records, so it configures its own masking and formatting, for example with `LogFormat.from_config(...)` (imported from `grpc_client`), which uses `configure_logging` values.

Read the call outcome from the record fields: `record.succeeded` distinguishes success from failure, and `record.is_stream` distinguishes a completed stream from a unary response. No need to interpret combinations of `status_code`, `message`, and `messages_count` yourself.

The client calls `is_enabled_for` before each record, so it must be cheap.

The sink must support calls from multiple threads and return quickly. If it raises an exception, the client suppresses it: the call succeeds, but the log record is lost.

A ready-to-use structlog implementation is in [`cloudru-qa-grpc-client-structlog`](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client-structlog).

### 12. Asynchronous client

`AsyncGRPCClient` provides the synchronous client's interface on top of `grpc.aio`:

```python
from grpc_client import AsyncGRPCClient, AsyncGRPCStreamResponse, GRPCResponse, options

from api import example_pb2, example_pb2_grpc


class MyAsyncClient(AsyncGRPCClient[example_pb2_grpc.ExampleStub]):
    @property
    def stub_class(self) -> type[example_pb2_grpc.ExampleStub]:
        return example_pb2_grpc.ExampleStub

    async def send_example_request(
        self,
        data: example_pb2.RequestMessage,
    ) -> GRPCResponse[example_pb2.ResponseMessage]:
        return await self.send_unary_unary_request(data, self.stub.ExampleMethod)


async with MyAsyncClient.from_addr("localhost:9000", options.with_insecure_channel()) as client:
    response = await client.send_example_request(data)
```

Differences from the synchronous client:

- sending methods must be awaited;
- streams return `AsyncGRPCStreamResponse`, read with `async for`, with status and metadata exposed as coroutines: `await stream.status_code()`;
- close with `await client.close()` or `async with`;
- `grpc.aio` interceptors can only be set when creating a channel, so `from_channel()` with options
  that add interceptors (`with_auth`, `with_logger`, `with_autogenerated_*`, `with_interceptor`)
  raises an error: create the channel yourself with `grpc.aio.insecure_channel(..., interceptors=[...])`
  or create the client with `from_addr()`;
- authorization requires an asynchronous `AsyncClientAuth` implementation with coroutine `token()` and `refresh()` methods.

Both clients share the same options: `options.with_logger(...)` selects the appropriate interceptor automatically.

### 13. Custom interceptors

An **interceptor** intercepts gRPC requests. Use it to add request data, collect metrics, or cache values.

Write interceptors using the regular grpcio API. To add metadata, inherit from `MetadataInterceptor`, which covers all four call types:

```python
from grpc_client.interceptors import MetadataInterceptor
from grpc_client.types import MetadataItems


class TenantInterceptor(MetadataInterceptor):
    """Add a tenant identifier to each request."""

    def __init__(self, tenant: str):
        self._tenant = tenant

    def metadata_to_add(self, call_details) -> MetadataItems:
        return (("x-tenant", self._tenant),)


client = MyCustomClient.from_addr(
    "localhost:9000",
    options.with_interceptor(TenantInterceptor("warehouse-42")),
)
```

The asynchronous client has `AsyncMetadataInterceptor` with the same contract, but `metadata_to_add` is a coroutine.

⚠️ Do not determine call success with `isinstance(outcome, grpc.RpcError)`: grpcio streaming call objects implement both `grpc.Call` and `grpc.RpcError` even for successful calls. Use the status code instead; the `grpc_client.interceptors.base.outcome_code` helper provides it.

ℹ️ Find more examples in the [library tests](https://github.com/cloud-ru-tech/qa-libraries/tree/master/packages/grpc-client/tests/).

## Development

The library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make,
and [`checkmake`](https://github.com/checkmake/checkmake).
Run commands from the repository root:

```shell
make sync                     # install dependencies for all libraries from uv.lock
make test-grpc-client         # tests for this library
make typecheck-grpc-client    # mypy for this library
make check                    # formatting, ruff, mypy, and tests for the entire workspace
```

⚠️ **Keep** the library lightweight and general-purpose. Discuss new dependencies
only when you are sure all library users need them.

Tests require Docker running: the [grpcbin](https://grpcb.in/) service container is started
and stopped automatically through [lovely-pytest-docker](https://github.com/lovelysystems/lovely-pytest-docker).
`make test-grpc-client` regenerates test `pb2.py` files from `proto/` before running;
run `make gen-test-api` for generation alone.

Tests run on Python 3.13 and 3.14. Create a separate environment for another version:
`make sync test-grpc-client PYTHON_VERSION=3.14`.

Publish a release with the git tag `grpc-client/v<version>`. The tag version must match the version
in `packages/grpc-client/pyproject.toml`, otherwise publication stops.
