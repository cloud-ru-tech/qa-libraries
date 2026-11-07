import asyncio
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, cast

import pytest
from explicit_wait import (
    AttemptsExhaustedError,
    Backoff,
    TimeoutExpiredError,
    WaitConfig,
    WaitOptions,
    configure,
    configured,
    get_config,
    reset_config,
    wait_for,
    wait_until,
)

from .fakes import FakeClock
from .matchers import assert_that
from .support import error_from

if TYPE_CHECKING:
    from explicit_wait.types import MaxAttempts

DEFAULT_TIMEOUT = 64.0
CONCURRENT_ROUNDS = 300


def test_default_timeout_is_sixty_four_seconds() -> None:
    assert_that(get_config().timeout_seconds).is_equal_to(DEFAULT_TIMEOUT)


def test_default_backoff_grows_from_two_to_sixty_four() -> None:
    assert_that(get_config().backoff).is_equal_to(
        Backoff(initial_seconds=2.0, maximum_seconds=64.0, multiplier=2.0),
    )


def test_default_has_no_attempt_limit() -> None:
    assert_that(get_config().max_attempts).is_none()


def test_configure_changes_the_timeout_used_by_waits(clock: FakeClock) -> None:
    configure(timeout_seconds=3.0, sleep_seconds=1.0)

    error = error_from(
        lambda: wait_until(lambda: None, clock=clock.monotonic, sleeper=clock.sleep),
        TimeoutExpiredError,
    )

    assert_that(error.timeout_seconds).is_equal_to(3.0)


def test_configure_changes_the_backoff_used_by_waits(clock: FakeClock) -> None:
    configure(timeout_seconds=20.0, sleep_seconds=(4.0, 4.0))

    error_from(
        lambda: wait_until(lambda: None, clock=clock.monotonic, sleeper=clock.sleep),
        TimeoutExpiredError,
    )

    assert_that(clock.sleeps).is_equal_to([4.0, 4.0, 4.0, 4.0])


def test_configure_changes_the_attempt_limit_used_by_waits(clock: FakeClock) -> None:
    configure(max_attempts=2, timeout_seconds=math.inf, sleep_seconds=1.0)

    error = error_from(
        lambda: wait_until(lambda: None, clock=clock.monotonic, sleeper=clock.sleep),
        AttemptsExhaustedError,
    )

    assert_that(error.attempts).is_equal_to(2)


def test_configure_keeps_untouched_values() -> None:
    configure(sleep_seconds=9.0)

    assert_that(get_config().timeout_seconds).is_equal_to(DEFAULT_TIMEOUT)


def test_configure_keeps_the_attempt_limit_when_it_is_not_given() -> None:
    configure(max_attempts=5)
    configure(timeout_seconds=10.0)

    assert_that(get_config().max_attempts).is_equal_to(5)


def test_configure_removes_the_attempt_limit_when_given_none() -> None:
    configure(max_attempts=5)

    configure(max_attempts=None)

    assert_that(get_config().max_attempts).is_none()


def test_temporary_override_removes_the_attempt_limit_when_given_none() -> None:
    configure(max_attempts=5)

    with configured(max_attempts=None):
        inside = get_config().max_attempts

    assert_that(inside).is_none()


def test_explicit_argument_wins_over_configuration(clock: FakeClock) -> None:
    configure(timeout_seconds=100.0, sleep_seconds=1.0)

    error = error_from(
        lambda: wait_until(
            lambda: None, options=WaitOptions(timeout_seconds=2.0), clock=clock.monotonic, sleeper=clock.sleep
        ),
        TimeoutExpiredError,
    )

    assert_that(error.timeout_seconds).is_equal_to(2.0)


def test_reset_restores_the_default_timeout() -> None:
    configure(timeout_seconds=1.0)

    reset_config()

    assert_that(get_config().timeout_seconds).is_equal_to(DEFAULT_TIMEOUT)


def test_configure_rejects_zero_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        configure(timeout_seconds=0.0)


def test_configure_rejects_negative_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        configure(timeout_seconds=-1.0)


def test_configure_rejects_not_a_number_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        configure(timeout_seconds=math.nan)


def test_configure_rejects_zero_max_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        configure(max_attempts=0)


@pytest.mark.parametrize("invalid", [1.5, math.nan, math.inf, True])
def test_configure_rejects_max_attempts_that_is_not_a_whole_number(invalid: object) -> None:
    with pytest.raises(TypeError, match="max_attempts"):
        configure(max_attempts=cast("MaxAttempts", invalid))


def test_configure_rejects_a_maximum_below_the_initial_interval() -> None:
    with pytest.raises(ValueError, match="maximum_seconds"):
        configure(sleep_seconds=(10.0, 1.0, 0.5))


def test_configure_rejects_a_shrinking_multiplier() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        configure(sleep_seconds=(1.0, 10.0, 0.5))


def test_failed_configure_leaves_the_previous_value() -> None:
    configure(timeout_seconds=30.0)
    error_from(lambda: configure(timeout_seconds=45.0, max_attempts=-1), ValueError)

    assert_that(get_config().timeout_seconds).is_equal_to(30.0)


def test_concurrent_configure_keeps_every_update() -> None:
    expected_timeout = 10.0
    rounds = (_configure_from_two_threads() for _ in range(CONCURRENT_ROUNDS))

    lost = [
        config
        for config in rounds
        if config.timeout_seconds != expected_timeout or config.backoff.initial_seconds != 1.0
    ]

    assert_that(lost).is_empty()


def test_temporary_override_applies_inside_the_block() -> None:
    with configured(timeout_seconds=7.0):
        inside = get_config().timeout_seconds

    assert_that(inside).is_equal_to(7.0)


def test_temporary_override_is_removed_after_the_block() -> None:
    with configured(timeout_seconds=7.0):
        pass

    assert_that(get_config().timeout_seconds).is_equal_to(DEFAULT_TIMEOUT)


def test_temporary_override_is_removed_after_an_exception() -> None:
    failure = RuntimeError("тест упал внутри блока")

    def fail_inside_the_block() -> None:
        with configured(timeout_seconds=5.0):
            raise failure

    error_from(fail_inside_the_block, RuntimeError)

    assert_that(get_config().timeout_seconds).is_equal_to(DEFAULT_TIMEOUT)


def test_temporary_overrides_nest() -> None:
    with configured(timeout_seconds=10.0), configured(sleep_seconds=1.0):
        inside = get_config()

    assert_that(inside.timeout_seconds).is_equal_to(10.0)


def test_temporary_override_restores_the_configured_baseline() -> None:
    configure(timeout_seconds=25.0)

    with configured(timeout_seconds=1.0):
        pass

    assert_that(get_config().timeout_seconds).is_equal_to(25.0)


def test_temporary_override_reaches_a_task_started_inside_the_block() -> None:
    async def scenario() -> float:
        with configured(timeout_seconds=9.0):
            task = asyncio.create_task(_read_timeout())
            return await task

    assert_that(asyncio.run(scenario())).is_equal_to(9.0)


def test_temporary_override_does_not_reach_a_worker_thread() -> None:
    configure(timeout_seconds=7.0)

    with configured(timeout_seconds=3.0), ThreadPoolExecutor(max_workers=1) as pool:
        inside = pool.submit(lambda: get_config().timeout_seconds).result()

    assert_that(inside).is_equal_to(7.0)


def test_config_is_immutable() -> None:
    config = WaitConfig()
    attribute = "timeout_seconds"

    with pytest.raises(FrozenInstanceError):
        setattr(config, attribute, 1.0)


def test_reads_timeout_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_TIMEOUT_SECONDS", "12.5")

    assert_that(WaitConfig.from_env().timeout_seconds).is_equal_to(12.5)


def test_reads_a_constant_sleep_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_SLEEP_SECONDS", "3")

    assert_that(WaitConfig.from_env().backoff).is_equal_to(Backoff(initial_seconds=3.0))


def test_reads_a_growing_sleep_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_SLEEP_SECONDS", "1,32,4")

    assert_that(WaitConfig.from_env().backoff).is_equal_to(
        Backoff(initial_seconds=1.0, maximum_seconds=32.0, multiplier=4.0),
    )


def test_reads_an_unbounded_sleep_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_SLEEP_SECONDS", "5,none")

    assert_that(WaitConfig.from_env().backoff.maximum_seconds).is_none()


def test_reads_max_attempts_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_MAX_ATTEMPTS", "8")

    assert_that(WaitConfig.from_env().max_attempts).is_equal_to(8)


def test_supports_a_custom_environment_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_TIMEOUT_SECONDS", "21")

    assert_that(WaitConfig.from_env(prefix="QA_").timeout_seconds).is_equal_to(21.0)


def test_keeps_defaults_when_the_environment_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_TIMEOUT_SECONDS", "")

    assert_that(WaitConfig.from_env().timeout_seconds).is_equal_to(DEFAULT_TIMEOUT)


def test_rejects_a_non_numeric_timeout_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_TIMEOUT_SECONDS", "быстро")

    with pytest.raises(ValueError, match="EXPLICIT_WAIT_TIMEOUT_SECONDS"):
        WaitConfig.from_env()


def test_rejects_a_non_integer_attempt_limit_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_MAX_ATTEMPTS", "2.5")

    with pytest.raises(ValueError, match="EXPLICIT_WAIT_MAX_ATTEMPTS"):
        WaitConfig.from_env()


def test_rejects_too_many_sleep_items_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLICIT_WAIT_SLEEP_SECONDS", "1,2,3,4")

    with pytest.raises(ValueError, match="EXPLICIT_WAIT_SLEEP_SECONDS"):
        WaitConfig.from_env()


def test_configuration_reaches_a_decorated_function(clock: FakeClock) -> None:
    configure(max_attempts=2, timeout_seconds=math.inf, sleep_seconds=1.0)

    @wait_for(clock=clock.monotonic, sleeper=clock.sleep)
    def never_ready() -> bool:
        return False

    error = error_from(never_ready, AttemptsExhaustedError)

    assert_that(error.attempts).is_equal_to(2)


async def _read_timeout() -> float:
    return get_config().timeout_seconds


def _configure_from_two_threads() -> WaitConfig:
    reset_config()
    start = threading.Event()

    def set_timeout() -> None:
        start.wait()
        configure(timeout_seconds=10.0)

    def set_sleep() -> None:
        start.wait()
        configure(sleep_seconds=1.0)

    workers = [threading.Thread(target=set_timeout), threading.Thread(target=set_sleep)]
    for worker in workers:
        worker.start()
    start.set()
    for worker in workers:
        worker.join()
    return get_config()


def test_configure_rejects_a_timeout_that_is_not_a_number() -> None:
    with pytest.raises(TypeError, match="timeout_seconds"):
        configure(timeout_seconds=cast("float", "быстро"))


def test_reuses_wait_options_without_mutating_shared_defaults(clock: FakeClock) -> None:
    options = WaitOptions(timeout_seconds=12.0, sleep_seconds=0.5, max_attempts=2)
    before = get_config()
    wait_until(lambda: "ready", options=options, clock=clock.monotonic, sleeper=clock.sleep)

    assert_that(get_config()).is_equal_to(before)


def test_reuses_wait_options_for_separate_waits(clock: FakeClock) -> None:
    options = WaitOptions(max_attempts=1)
    wait_until(lambda: "first", options=options, clock=clock.monotonic, sleeper=clock.sleep)

    assert_that(wait_until(lambda: "second", options=options, clock=clock.monotonic, sleeper=clock.sleep)).is_equal_to(
        "second"
    )
