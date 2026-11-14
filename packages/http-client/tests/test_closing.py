import pytest
from assertpy import assert_that
from http_client.client import AsyncHttpClient, HttpClient


def test_close_closes_transport() -> None:
    """close() closes the connection pool."""
    client = HttpClient("https://vault.example.com")

    client.close()

    assert_that(client.client.is_closed).is_true()


def test_client_stays_open_inside_context() -> None:
    """The connection pool is open inside the context manager."""
    with HttpClient("https://cdn.example.com") as client:
        assert_that(client.client.is_closed).is_false()


def test_context_manager_closes_transport() -> None:
    """Leaving the context manager closes the connection pool."""
    with HttpClient("https://logs.example.com") as client:
        pass

    assert_that(client.client.is_closed).is_true()


def test_reopening_closed_client_is_rejected() -> None:
    """Reentering a closed client is forbidden, as in httpx."""
    client = HttpClient("https://metrics.example.com")
    with client:
        pass

    with pytest.raises(RuntimeError), client:
        pass


async def test_aclose_closes_transport() -> None:
    """aclose() closes the asynchronous client connection pool."""
    client = AsyncHttpClient("https://queue.example.com")

    await client.aclose()

    assert_that(client.client.is_closed).is_true()


async def test_async_client_stays_open_inside_context() -> None:
    """The connection pool is open inside the asynchronous context manager."""
    async with AsyncHttpClient("https://search.example.com") as client:
        assert_that(client.client.is_closed).is_false()


async def test_async_context_manager_closes_transport() -> None:
    """Leaving the asynchronous context manager closes the connection pool."""
    async with AsyncHttpClient("https://mail.example.com") as client:
        pass

    assert_that(client.client.is_closed).is_true()


async def test_reopening_closed_async_client_is_rejected() -> None:
    """Reentering a closed asynchronous client is forbidden, as in httpx."""
    client = AsyncHttpClient("https://backup.example.com")
    async with client:
        pass

    with pytest.raises(RuntimeError):
        async with client:
            pass
