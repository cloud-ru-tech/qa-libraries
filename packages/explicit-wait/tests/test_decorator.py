import asyncio

from explicit_wait import InvalidPredicateError, TimeoutExpiredError, WaitOptions, async_wait_for, wait_for

from .fakes import FakeClock
from .matchers import assert_that
from .support import error_from


def test_returns_the_first_truthy_result(clock: FakeClock) -> None:
    required_attempts = 3
    attempts: list[int] = []

    @wait_for(options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0), clock=clock.monotonic, sleeper=clock.sleep)
    def deploy_finished() -> str | None:
        attempts.append(1)
        return "готов" if len(attempts) >= required_attempts else None

    assert_that(deploy_finished()).is_equal_to("готов")


def test_passes_arguments_through(clock: FakeClock) -> None:
    @wait_for(options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0), clock=clock.monotonic, sleeper=clock.sleep)
    def echo(prefix: str, *, suffix: str) -> str:
        return f"{prefix}-{suffix}"

    assert_that(echo("узел", suffix="поднят")).is_equal_to("узел-поднят")


def test_keeps_the_wrapped_function_name(clock: FakeClock) -> None:
    @wait_for(options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0), clock=clock.monotonic, sleeper=clock.sleep)
    def cluster_is_healthy() -> bool:
        return True

    assert_that(cluster_is_healthy.__name__).is_equal_to("cluster_is_healthy")


def test_uses_the_function_name_in_the_error(clock: FakeClock) -> None:
    @wait_for(options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0), clock=clock.monotonic, sleeper=clock.sleep)
    def index_is_rebuilt() -> bool:
        return False

    error = error_from(index_is_rebuilt, TimeoutExpiredError)

    assert_that(str(error)).contains("index_is_rebuilt")


def test_async_decorator_returns_the_first_truthy_result(clock: FakeClock) -> None:
    required_attempts = 2
    attempts: list[int] = []

    @async_wait_for(
        options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0), clock=clock.monotonic, sleeper=clock.async_sleep
    )
    async def migration_finished() -> str | None:
        attempts.append(1)
        return "применена" if len(attempts) >= required_attempts else None

    assert_that(asyncio.run(migration_finished())).is_equal_to("применена")


def test_async_decorator_uses_the_function_name_in_the_error(clock: FakeClock) -> None:
    @async_wait_for(
        options=WaitOptions(timeout_seconds=4.0, sleep_seconds=1.0), clock=clock.monotonic, sleeper=clock.async_sleep
    )
    async def queue_is_drained() -> bool:
        return False

    error = error_from(lambda: asyncio.run(queue_is_drained()), TimeoutExpiredError)

    assert_that(str(error)).contains("queue_is_drained")


def test_rejects_an_asynchronous_function_at_decoration_time(clock: FakeClock) -> None:
    async def deploy_finished() -> bool:
        return False

    decorate = wait_for(options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0), clock=clock.monotonic)
    error = error_from(lambda: decorate(deploy_finished), InvalidPredicateError)

    assert_that(str(error)).contains("async_wait_for")
