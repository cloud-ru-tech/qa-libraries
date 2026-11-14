import httpx
from assertpy import assert_that
from http_client.options import with_request_hook, with_response_hook
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


async def test_awaits_async_callable_object_hook(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Run a hook object with `async def __call__`.

    Regression: iscoroutinefunction does not recognize such an object, and the wrapper
    returned an unawaited coroutine, silently skipping the hook.
    """
    seen: list[str] = []

    class Hook:
        async def __call__(self, request: httpx.Request) -> None:
            seen.append(str(request.url))

    httpx_mock.add_response(status_code=200)
    client = new_async_client("https://example.com", with_request_hook(Hook()))

    await client.get("/api/test")

    assert_that(seen).is_equal_to(["https://example.com/api/test"])


async def test_runs_sync_callable_object_hook_in_async_client(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """A hook object with a regular `__call__` also runs in the asynchronous client."""
    seen: list[str] = []

    class Hook:
        def __call__(self, request: httpx.Request) -> None:
            seen.append(str(request.url))

    httpx_mock.add_response(status_code=200)
    client = new_async_client("https://example.com", with_request_hook(Hook()))

    await client.get("/api/report")

    assert_that(seen).is_equal_to(["https://example.com/api/report"])


def test_runs_request_hooks_in_order_of_registration(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Hooks run in insertion order."""
    calls: list[str] = []
    httpx_mock.add_response(status_code=200)
    client = new_client(
        "https://example.com",
        with_request_hook(lambda _request: calls.append("first")),
        with_request_hook(lambda _request: calls.append("second")),
    )

    client.get("/api/test")

    assert_that(calls).is_equal_to(["first", "second"])


async def test_runs_sync_and_async_hooks_together(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Mixed synchronous and asynchronous hooks run in insertion order."""
    calls: list[str] = []

    async def async_hook(_request: httpx.Request) -> None:
        calls.append("async")

    httpx_mock.add_response(status_code=200)
    client = new_async_client(
        "https://example.com",
        with_request_hook(lambda _request: calls.append("sync")),
        with_request_hook(async_hook),
    )

    await client.get("/api/test")

    assert_that(calls).is_equal_to(["sync", "async"])


def test_response_hook_receives_received_response(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """The response hook receives the server response."""
    statuses: list[int] = []
    httpx_mock.add_response(status_code=418)
    client = new_client(
        "https://example.com",
        with_response_hook(lambda response: statuses.append(response.status_code)),
    )

    client.get("/api/teapot")

    assert_that(statuses).is_equal_to([418])


def test_runs_request_hook_for_stream_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Run the request hook for streaming requests too."""
    seen: list[str] = []
    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_client("https://example.com", with_request_hook(lambda request: seen.append(str(request.url))))

    with client.stream_request(httpx.Request("GET", "https://example.com/data")) as response:
        response.read()

    assert_that(seen).is_equal_to(["https://example.com/data"])


def test_runs_response_hook_for_stream_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Run the response hook for streaming requests too."""
    statuses: list[int] = []
    httpx_mock.add_response(status_code=206, content=b"chunk")
    client = new_client(
        "https://example.com",
        with_response_hook(lambda response: statuses.append(response.status_code)),
    )

    with client.stream_request(httpx.Request("GET", "https://example.com/data")) as response:
        response.read()

    assert_that(statuses).is_equal_to([206])


async def test_runs_sync_hook_for_async_stream_request(
    httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory
) -> None:
    """Run a synchronous hook for an asynchronous client streaming request."""
    seen: list[str] = []
    httpx_mock.add_response(status_code=200, content=b"streamed")
    client = new_async_client("https://example.com", with_request_hook(lambda request: seen.append(str(request.url))))

    async with client.stream_request(httpx.Request("GET", "https://example.com/feed")) as response:
        await response.aread()

    assert_that(seen).is_equal_to(["https://example.com/feed"])


def test_stream_request_passes_the_same_request_object_to_hooks(
    httpx_mock: HTTPXMock,
    new_client: SyncClientFactory,
) -> None:
    """Hooks receive the same Request object supplied to stream_request."""
    seen: list[int] = []
    httpx_mock.add_response(status_code=200, content=b"x")
    client = new_client("https://example.com", with_request_hook(lambda request: seen.append(id(request))))
    request = client.client.build_request("GET", "/data")

    with client.stream_request(request) as response:
        response.read()

    assert_that(seen).is_equal_to([id(request)])


async def test_async_stream_request_passes_the_same_request_object_to_hooks(
    httpx_mock: HTTPXMock,
    new_async_client: AsyncClientFactory,
) -> None:
    """Asynchronous client hooks receive the same Request object supplied to stream_request."""
    seen: list[int] = []
    httpx_mock.add_response(status_code=200, content=b"x")
    client = new_async_client("https://example.com", with_request_hook(lambda request: seen.append(id(request))))
    request = client.client.build_request("GET", "/data")

    async with client.stream_request(request) as response:
        await response.aread()

    assert_that(seen).is_equal_to([id(request)])
