import inspect
import time
from types import ModuleType
from typing import TYPE_CHECKING, cast

import explicit_wait
import pytest
from explicit_wait import wait_until

from .matchers import assert_that

if TYPE_CHECKING:
    from collections.abc import Callable


def test_wait_until_is_callable() -> None:
    assert_that(callable(wait_until)).is_true()


def test_no_exported_name_is_shadowed_by_a_submodule() -> None:
    shadowed = [
        name for name in explicit_wait.__all__ if isinstance(cast("object", getattr(explicit_wait, name)), ModuleType)
    ]
    assert_that(shadowed).is_empty()


def test_every_exported_name_is_importable() -> None:
    missing = [name for name in explicit_wait.__all__ if not hasattr(explicit_wait, name)]
    assert_that(missing).is_empty()


def test_wait_until_measures_time_with_monotonic_clock() -> None:
    default_clock = cast("object", inspect.signature(wait_until).parameters["clock"].default)
    assert_that(default_clock).is_same_as(time.monotonic)


def test_wait_until_rejects_positional_options() -> None:
    call = cast("Callable[[Callable[[], object], int], object]", wait_until)

    with pytest.raises(TypeError):
        call(lambda: True, 30)


def test_public_api_contains_exactly_the_documented_names() -> None:
    assert_that(set(explicit_wait.__all__)).is_equal_to(
        {
            "AllOf",
            "AnyOf",
            "AsyncAllOf",
            "AsyncAnyOf",
            "Attempt",
            "AttemptsExhaustedError",
            "Backoff",
            "InvalidPredicateError",
            "MaxAttempts",
            "TimeoutExpiredError",
            "UNSET",
            "WaitCancelledError",
            "WaitConfig",
            "WaitOptions",
            "WaitError",
            "WaitStoppedError",
            "async_wait_for",
            "async_wait_or_none",
            "async_wait_until",
            "async_wait_while",
            "configure",
            "configured",
            "get_config",
            "reset_config",
            "wait_for",
            "wait_or_none",
            "wait_until",
            "wait_while",
        },
    )
