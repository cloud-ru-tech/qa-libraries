from datetime import UTC, datetime, timedelta

from http_client_auth import InMemoryAsyncAuthStore, InMemoryAuthStore, Token
from http_client_auth.store import DEFAULT_EXPIRY_LEEWAY

from .assertions import assert_that


def test_keeps_long_lived_token_usable() -> None:
    """A newly issued long-lived token is not expired."""
    token = Token.with_lifetime("session-token", 3600)

    assert_that(token.is_expired).is_false()


def test_keeps_short_lived_token_usable() -> None:
    """A newly issued token with a lifetime shorter than the margin is not expired."""
    token = Token.with_lifetime("one-time-token", 10)

    assert_that(token.is_expired).is_false()


def test_expires_token_earlier_than_declared_lifetime() -> None:
    """The token becomes invalid by the margin before the service-declared expiration time."""
    lifetime = timedelta(hours=1)
    tolerance = timedelta(seconds=5)

    token = Token.with_lifetime("delivery-token", int(lifetime.total_seconds()))

    assert_that(token.expires_at).is_before(datetime.now(UTC) + lifetime - DEFAULT_EXPIRY_LEEWAY + tolerance)


def test_reserves_no_more_than_default_leeway() -> None:
    """The margin subtracted from the lifetime does not exceed DEFAULT_EXPIRY_LEEWAY."""
    lifetime = timedelta(hours=1)
    tolerance = timedelta(seconds=5)

    token = Token.with_lifetime("warehouse-token", int(lifetime.total_seconds()))

    assert_that(token.expires_at).is_after(datetime.now(UTC) + lifetime - DEFAULT_EXPIRY_LEEWAY - tolerance)


def test_marks_token_expired_after_deadline() -> None:
    """A token past its expiration time is expired."""
    token = Token("stale-token", datetime.now(UTC) - timedelta(seconds=1))

    assert_that(token.is_expired).is_true()


def test_returns_saved_token() -> None:
    """The store returns the stored token for the same key."""
    store = InMemoryAuthStore()
    token = Token.with_lifetime("analytics-token", 3600)

    store.set("analytics-key", token)

    assert_that(store.get("analytics-key")).is_equal_to(token)


def test_returns_nothing_for_unknown_key() -> None:
    """The store returns nothing for an unknown key."""
    store = InMemoryAuthStore()

    assert_that(store.get("never-saved-key")).is_none()


async def test_async_returns_saved_token() -> None:
    """The asynchronous store returns the stored token for the same key."""
    store = InMemoryAsyncAuthStore()
    token = Token.with_lifetime("streaming-token", 3600)

    await store.set("streaming-key", token)

    assert_that(await store.get("streaming-key")).is_equal_to(token)


async def test_async_returns_nothing_for_unknown_key() -> None:
    """The asynchronous store returns nothing for an unknown key."""
    store = InMemoryAsyncAuthStore()

    assert_that(await store.get("never-saved-key")).is_none()
