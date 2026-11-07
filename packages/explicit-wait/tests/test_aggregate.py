import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest
from explicit_wait import (
    AllOf,
    AnyOf,
    AsyncAllOf,
    AsyncAnyOf,
    AttemptsExhaustedError,
    InvalidPredicateError,
    TimeoutExpiredError,
    WaitOptions,
    async_wait_until,
    wait_or_none,
    wait_until,
)
from explicit_wait.aggregate import Aggregate, AsyncAggregate

from .fakes import (
    AwaitableTrackingClose,
    AwaitableWithBrokenClose,
    AwaitableWithoutClose,
    FakeClock,
    started_awaitable_that_refuses_to_close,
)
from .matchers import assert_that
from .support import async_error_from, error_from

CONCURRENT_WORKERS = 8
CONCURRENT_CALLS = 40


async def _truthy() -> bool:
    return True


async def _falsy() -> bool:
    return False


def test_all_of_is_true_when_every_predicate_is_true() -> None:
    aggregate = AllOf([lambda: True, lambda: "данные", lambda: 1])

    assert_that(aggregate()).is_true()


def test_all_of_is_false_when_one_predicate_is_false() -> None:
    aggregate = AllOf([lambda: True, lambda: None])

    assert_that(aggregate()).is_false()


def test_all_of_re_evaluates_predicates_on_every_call() -> None:
    calls: list[str] = []

    def record() -> bool:
        calls.append("проверка")
        return True

    aggregate = AllOf([record])
    aggregate()
    aggregate()

    assert_that(calls).is_length(2)


def test_all_of_is_false_for_conditions_that_never_hold_together() -> None:
    status = "ready"
    aggregate = AllOf([lambda: status == "ready", lambda: status == "completed"])

    aggregate()
    status = "completed"

    assert_that(aggregate()).is_false()


def test_all_of_keeps_its_predicates_after_a_successful_call() -> None:
    aggregate = AllOf([lambda: True, lambda: True])

    aggregate()

    assert_that(aggregate.predicates).is_length(2)


def test_all_of_stores_predicates_immutably() -> None:
    aggregate = AllOf([lambda: True])

    assert_that(aggregate.predicates).is_instance_of(tuple)


def test_all_of_calls_predicates_in_declaration_order() -> None:
    order: list[str] = []

    def record_first() -> bool:
        order.append("первый")
        return True

    def record_second() -> bool:
        order.append("второй")
        return True

    AllOf([record_first, record_second])()

    assert_that(order).is_equal_to(["первый", "второй"])


def test_all_of_stops_at_the_first_false_predicate() -> None:
    calls: list[str] = []

    def record() -> bool:
        calls.append("не должен вызываться")
        return True

    AllOf([lambda: False, record])()

    assert_that(calls).is_empty()


def test_all_of_survives_concurrent_calls() -> None:
    aggregate = AllOf([lambda: True, lambda: True, lambda: True])

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool:
        results = list(pool.map(lambda _: aggregate(), range(CONCURRENT_CALLS)))

    assert_that([result for result in results if result is not True]).is_empty()


def test_any_of_is_true_when_one_predicate_is_true() -> None:
    aggregate = AnyOf([lambda: False, lambda: "нашли", lambda: None])

    assert_that(aggregate()).is_true()


def test_any_of_is_false_when_every_predicate_is_false() -> None:
    aggregate = AnyOf([lambda: 0, lambda: ""])

    assert_that(aggregate()).is_false()


def test_any_of_stops_at_the_first_true_predicate() -> None:
    calls: list[str] = []

    def record() -> bool:
        calls.append("не должен вызываться")
        return True

    AnyOf([lambda: True, record])()

    assert_that(calls).is_empty()


def test_all_of_rejects_an_empty_predicate_list() -> None:
    with pytest.raises(ValueError, match="at least one predicate"):
        AllOf([])


def test_any_of_rejects_an_empty_predicate_list() -> None:
    with pytest.raises(ValueError, match="at least one predicate"):
        AnyOf([])


def test_base_aggregate_is_abstract() -> None:
    assert_that(inspect.isabstract(Aggregate)).is_true()


def test_aggregates_accept_a_generator_of_predicates() -> None:
    aggregate = AllOf(lambda: True for _ in range(3))

    assert_that(aggregate()).is_true()


def test_and_operator_builds_a_conjunction() -> None:
    aggregate = AnyOf([lambda: True]) & (lambda: False)

    assert_that(aggregate()).is_false()


def test_or_operator_builds_a_disjunction() -> None:
    aggregate = AllOf([lambda: False]) | (lambda: True)

    assert_that(aggregate()).is_true()


def test_nested_aggregate_works_inside_a_wait(clock: FakeClock) -> None:
    required_attempts = 3
    attempts: list[int] = []

    def cache_warm() -> bool:
        attempts.append(1)
        return len(attempts) >= required_attempts

    aggregate = AllOf([AnyOf([lambda: True]), cache_warm])

    result = wait_until(
        aggregate,
        options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert_that(result).is_true()


def test_the_same_aggregate_still_checks_conditions_in_a_second_wait(clock: FakeClock) -> None:
    ready = {"value": True}
    aggregate = AllOf([lambda: ready["value"]])
    wait_until(
        aggregate,
        options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0),
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )
    ready["value"] = False

    error_from(
        lambda: wait_until(
            aggregate,
            options=WaitOptions(timeout_seconds=3.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        TimeoutExpiredError,
    )

    assert_that(aggregate()).is_false()


def test_sync_aggregate_rejects_an_asynchronous_predicate() -> None:
    with pytest.raises(TypeError, match="AsyncAllOf"):
        AllOf([_falsy])()


def test_async_all_of_is_true_when_every_predicate_is_true() -> None:
    assert_that(asyncio.run(AsyncAllOf([_truthy, _truthy])())).is_true()


def test_async_all_of_is_false_when_one_predicate_is_false() -> None:
    assert_that(asyncio.run(AsyncAllOf([_truthy, _falsy])())).is_false()


def test_async_any_of_is_true_when_one_predicate_is_true() -> None:
    assert_that(asyncio.run(AsyncAnyOf([_falsy, _truthy])())).is_true()


def test_async_any_of_is_false_when_every_predicate_is_false() -> None:
    assert_that(asyncio.run(AsyncAnyOf([_falsy, _falsy])())).is_false()


def test_async_aggregate_accepts_a_plain_predicate() -> None:
    assert_that(asyncio.run(AsyncAllOf([lambda: True, _truthy])())).is_true()


def test_async_all_of_stops_at_the_first_false_predicate() -> None:
    calls: list[str] = []

    async def record() -> bool:
        calls.append("не должен вызываться")
        return True

    asyncio.run(AsyncAllOf([_falsy, record])())

    assert_that(calls).is_empty()


def test_async_any_of_stops_at_the_first_true_predicate() -> None:
    calls: list[str] = []

    async def record() -> bool:
        calls.append("не должен вызываться")
        return True

    asyncio.run(AsyncAnyOf([_truthy, record])())

    assert_that(calls).is_empty()


def test_base_async_aggregate_is_abstract() -> None:
    assert_that(inspect.isabstract(AsyncAggregate)).is_true()


def test_async_aggregate_rejects_an_empty_predicate_list() -> None:
    with pytest.raises(ValueError, match="at least one predicate"):
        AsyncAllOf([])


def test_async_and_operator_builds_a_conjunction() -> None:
    aggregate = AsyncAnyOf([_truthy]) & _falsy

    assert_that(asyncio.run(aggregate())).is_false()


def test_async_or_operator_builds_a_disjunction() -> None:
    aggregate = AsyncAllOf([_falsy]) | _truthy

    assert_that(asyncio.run(aggregate())).is_true()


def test_async_aggregate_that_never_holds_does_not_pass_the_wait(clock: FakeClock) -> None:
    error = async_error_from(
        async_wait_until(
            AsyncAllOf([_truthy, _falsy]),
            options=WaitOptions(timeout_seconds=100.0, sleep_seconds=1.0, max_attempts=3),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        AttemptsExhaustedError,
    )

    assert_that(error.attempts).is_equal_to(3)


def test_async_aggregate_passes_the_wait_when_conditions_hold(clock: FakeClock) -> None:
    result = asyncio.run(
        async_wait_until(
            AsyncAllOf([_truthy, _truthy]),
            options=WaitOptions(timeout_seconds=30.0, sleep_seconds=1.0),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
    )

    assert_that(result).is_true()


def test_sync_aggregate_rejects_an_awaitable_without_close() -> None:
    with pytest.raises(TypeError, match="AsyncAllOf"):
        AllOf([AwaitableWithoutClose])()


def test_async_aggregate_exposes_its_predicates() -> None:
    aggregate = AsyncAllOf([_truthy, _falsy])

    assert_that(aggregate.predicates).is_length(2)


def test_broken_close_does_not_replace_the_rejection_error() -> None:
    with pytest.raises(TypeError, match="AsyncAllOf"):
        AllOf([AwaitableWithBrokenClose])()


def test_rejected_coroutine_is_closed() -> None:
    coroutine = _falsy()
    error_from(AllOf([lambda: coroutine]), InvalidPredicateError)

    assert_that(inspect.getcoroutinestate(coroutine)).is_equal_to(inspect.CORO_CLOSED)


def test_failing_close_of_a_coroutine_does_not_replace_the_rejection_error() -> None:
    awaitable = started_awaitable_that_refuses_to_close()

    with pytest.raises(TypeError, match="AsyncAllOf"):
        AllOf([lambda: awaitable])()


def test_user_close_is_not_called_for_an_arbitrary_awaitable() -> None:
    awaitable = AwaitableTrackingClose()
    error_from(AllOf([lambda: awaitable]), InvalidPredicateError)

    assert_that(awaitable.close_called).is_false()


def test_aggregate_rejection_is_not_swallowed_by_a_broad_exception_filter(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_until(
            AllOf([_falsy]),
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("AsyncAllOf")


def test_aggregate_rejection_is_not_converted_to_none(clock: FakeClock) -> None:
    error = error_from(
        lambda: wait_or_none(
            AllOf([_falsy]),
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
            sleeper=clock.sleep,
        ),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("AsyncAllOf")


def test_async_aggregate_rejection_is_not_swallowed(clock: FakeClock) -> None:
    error = async_error_from(
        async_wait_until(
            AllOf([_falsy]),
            options=WaitOptions(timeout_seconds=5.0, sleep_seconds=1.0, expected_exceptions=Exception),
            clock=clock.monotonic,
            sleeper=clock.async_sleep,
        ),
        InvalidPredicateError,
    )

    assert_that(str(error)).contains("AsyncAllOf")


def test_invalid_predicate_error_is_a_type_error() -> None:
    assert_that(issubclass(InvalidPredicateError, TypeError)).is_true()
