import httpx
from assertpy import assert_that
from http_client.options import with_request_hook, with_response_hook
from pytest_httpx import HTTPXMock

from .support.clients import AsyncClientFactory, SyncClientFactory


async def test_awaits_async_callable_object_hook(httpx_mock: HTTPXMock, new_async_client: AsyncClientFactory) -> None:
    """Хук-объект с `async def __call__` выполняется.

    Регрессия: iscoroutinefunction не распознаёт такой объект, и обёртка
    возвращала невыполненную корутину, молча пропуская хук.
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
    """Хук-объект с обычным `__call__` тоже выполняется в асинхронном клиенте."""
    seen: list[str] = []

    class Hook:
        def __call__(self, request: httpx.Request) -> None:
            seen.append(str(request.url))

    httpx_mock.add_response(status_code=200)
    client = new_async_client("https://example.com", with_request_hook(Hook()))

    await client.get("/api/report")

    assert_that(seen).is_equal_to(["https://example.com/api/report"])


def test_runs_request_hooks_in_order_of_registration(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Хуки выполняются в порядке добавления."""
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
    """Смешанные синхронные и асинхронные хуки выполняются в порядке добавления."""
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
    """Хук ответа получает полученный от сервера ответ."""
    statuses: list[int] = []
    httpx_mock.add_response(status_code=418)
    client = new_client(
        "https://example.com",
        with_response_hook(lambda response: statuses.append(response.status_code)),
    )

    client.get("/api/teapot")

    assert_that(statuses).is_equal_to([418])


def test_runs_request_hook_for_stream_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Хук запроса выполняется и для потокового запроса."""
    seen: list[str] = []
    httpx_mock.add_response(status_code=200, content=b"chunk")
    client = new_client("https://example.com", with_request_hook(lambda request: seen.append(str(request.url))))

    with client.stream_request(httpx.Request("GET", "https://example.com/data")) as response:
        response.read()

    assert_that(seen).is_equal_to(["https://example.com/data"])


def test_runs_response_hook_for_stream_request(httpx_mock: HTTPXMock, new_client: SyncClientFactory) -> None:
    """Хук ответа выполняется и для потокового запроса."""
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
    """Синхронный хук выполняется для потокового запроса асинхронного клиента."""
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
    """Хуки получают тот же объект Request, что передан в stream_request."""
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
    """Хуки асинхронного клиента получают тот же объект Request, что передан в stream_request."""
    seen: list[int] = []
    httpx_mock.add_response(status_code=200, content=b"x")
    client = new_async_client("https://example.com", with_request_hook(lambda request: seen.append(id(request))))
    request = client.client.build_request("GET", "/data")

    async with client.stream_request(request) as response:
        await response.aread()

    assert_that(seen).is_equal_to([id(request)])
