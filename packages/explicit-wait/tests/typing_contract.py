from collections.abc import Awaitable
from typing import assert_type

from explicit_wait import async_wait_or_none, async_wait_until, wait_or_none, wait_until


async def _coroutine_predicate() -> str | None:
    return "готово"


def _plain_predicate() -> str | None:
    return "готово"


def _awaitable_predicate() -> Awaitable[str] | None:
    return None


def _mixed_predicate() -> str | Awaitable[str] | None:
    return None


async def check_async_overloads() -> None:
    """Закрепить вывод типов перегрузок: этот модуль проверяется mypy, а не pytest."""
    assert_type(await async_wait_until(_coroutine_predicate), str)
    assert_type(await async_wait_until(_plain_predicate), str)
    assert_type(await async_wait_until(_awaitable_predicate), str)
    assert_type(await async_wait_until(_mixed_predicate), str)
    assert_type(await async_wait_or_none(_coroutine_predicate), str | None)
    assert_type(await async_wait_or_none(_mixed_predicate), str | None)


def check_sync_signatures() -> None:
    """Закрепить вывод типов синхронных функций ожидания."""
    assert_type(wait_until(_plain_predicate), str)
    assert_type(wait_or_none(_plain_predicate), str | None)
