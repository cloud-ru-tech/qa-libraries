import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import tenacity
from tenacity.stop import StopBaseT
from tenacity.wait import WaitBaseT

DEFAULT_RETRIES_STOP = tenacity.stop_after_attempt(5)
# Jitter is required: without it all clients retry simultaneously after a shared failure.
DEFAULT_RETRIES_WAIT = tenacity.wait_exponential_jitter(initial=1, max=64, jitter=1)
DEFAULT_MAX_RETRY_AFTER = 60.0

RetryHookT = Callable[[tenacity.RetryCallState], Awaitable[None] | None]


class _Unset(Enum):
    """Distinguish an omitted parameter from an explicit None."""

    MARKER = "unset"

    def __repr__(self) -> str:
        return "UNSET"


#: Default override value: inherit the global configuration.
#: Keep it separate from `None`, because `None` is a meaningful value for `before_sleep_hook`
#: and means that the hook is disabled for this client.
UNSET: Literal[_Unset.MARKER] = _Unset.MARKER

type Unset = Literal[_Unset.MARKER]


@dataclass(frozen=True, kw_only=True)
class Config:
    """Immutable retry policy: `configure()` replaces it in full."""

    stop: StopBaseT = DEFAULT_RETRIES_STOP
    wait: WaitBaseT = DEFAULT_RETRIES_WAIT
    before_sleep_hook: RetryHookT | None = None
    reraise: bool = False
    respect_retry_after: bool = True
    max_retry_after: float = DEFAULT_MAX_RETRY_AFTER


@dataclass(frozen=True, kw_only=True)
class RetryOverrides:
    """Individual policy overrides for one client.

    Read fields left `UNSET` from the global configuration at request time,
    rather than client creation time. An explicit `None` for `before_sleep_hook` disables the hook
    for this client.
    """

    stop: StopBaseT | Unset = UNSET
    wait: WaitBaseT | Unset = UNSET
    before_sleep_hook: RetryHookT | Unset | None = UNSET
    reraise: bool | Unset = UNSET
    respect_retry_after: bool | Unset = UNSET
    max_retry_after: float | Unset = UNSET

    def apply_to(self, base: Config) -> Config:
        """Apply overrides to the current configuration.

        :param base: Global settings snapshot.
        :return: Client settings with overrides applied.
        """
        values = (
            self.stop,
            self.wait,
            self.before_sleep_hook,
            self.reraise,
            self.respect_retry_after,
            self.max_retry_after,
        )
        if all(value is UNSET for value in values):
            return base
        return Config(
            stop=_select(self.stop, base.stop),
            wait=_select(self.wait, base.wait),
            before_sleep_hook=_select(self.before_sleep_hook, base.before_sleep_hook),
            reraise=_select(self.reraise, base.reraise),
            respect_retry_after=_select(self.respect_retry_after, base.respect_retry_after),
            max_retry_after=_select(self.max_retry_after, base.max_retry_after),
        )

    def merge(self, other: "RetryOverrides") -> "RetryOverrides":
        """Merge overrides from two options for the same client.

        The client uses a single policy, so each parameter must be set in exactly one option.
        Do not compare values semantically: tenacity strategies lack `__eq__`,
        and shallow comparison of hook functions could treat different objects as equal
        and silently discard one of them.
        """
        return RetryOverrides(
            stop=_merge_override("stop", self.stop, other.stop),
            wait=_merge_override("wait", self.wait, other.wait),
            before_sleep_hook=_merge_override("before_sleep_hook", self.before_sleep_hook, other.before_sleep_hook),
            reraise=_merge_override("reraise", self.reraise, other.reraise),
            respect_retry_after=_merge_override(
                "respect_retry_after", self.respect_retry_after, other.respect_retry_after
            ),
            max_retry_after=_merge_override("max_retry_after", self.max_retry_after, other.max_retry_after),
        )


def _select[T](value: T | Unset, default: T) -> T:
    return default if value is UNSET else value


def _merge_override[T](name: str, mine: T | Unset, theirs: T | Unset) -> T | Unset:
    if mine is not UNSET and theirs is not UNSET:
        message = (
            f"Параметр {name} задан сразу в двух опциях повторов одного клиента "
            f"({mine!r} и {theirs!r}). Укажите его только в одной из них."
        )
        raise ValueError(message)
    return mine if mine is not UNSET else theirs


NO_OVERRIDES = RetryOverrides()


class _State:
    current = Config()


def configure(*, options: Config | None = None) -> None:
    """Replace the global retry policy with a single snapshot.

    :param options: Retry settings; None restores defaults.
    :raises ValueError: If the Retry-After limit is not a finite nonnegative number.
    """
    snapshot = Config() if options is None else options
    if not math.isfinite(snapshot.max_retry_after) or snapshot.max_retry_after < 0:
        message = f"max_retry_after должен быть конечным неотрицательным числом, получено {snapshot.max_retry_after!r}"
        raise ValueError(message)
    _State.current = snapshot


def get_config() -> Config:
    """Return the current global policy as a safe, immutable snapshot."""
    return _State.current
