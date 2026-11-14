import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .attempt import Attempt
from .backoff import FULL_TUPLE_LENGTH, SHORT_TUPLE_LENGTH, TUPLE_MULTIPLIER, Backoff, SleepSecondsType
from .types import UNSET, ExceptionFilter, ExceptionsType, MaxAttempts
from .validators import validate_max_attempts, validate_timeout_seconds

DEFAULT_TIMEOUT_SECONDS = 64.0
DEFAULT_BACKOFF = Backoff(initial_seconds=2.0, maximum_seconds=64.0, multiplier=2.0)
ENV_PREFIX = "EXPLICIT_WAIT_"
NONE_ALIASES = frozenset({"", "none", "null"})


@dataclass(frozen=True, slots=True)
class WaitConfig:
    """Default values for wait functions.

    The object is immutable: settings can only be replaced together, preventing
    a partially applied state with two inconsistent fields.
    """

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    backoff: Backoff = DEFAULT_BACKOFF
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        """Validate configuration values.

        :raises TypeError: if the time or attempt count has an invalid type.
        :raises ValueError: if values are outside the allowed bounds.
        """
        validate_timeout_seconds(self.timeout_seconds)
        validate_max_attempts(self.max_attempts)

    @classmethod
    def from_env(cls, prefix: str = ENV_PREFIX) -> "WaitConfig":
        """Build configuration from environment variables.

        Read ``<prefix>TIMEOUT_SECONDS``, ``<prefix>SLEEP_SECONDS``, and
        ``<prefix>MAX_ATTEMPTS``. Specify the pause as a number (``1.5``) or comma-separated
        values (``2,64`` or ``2,64,3``); ``none`` in the maximum position removes the limit.
        Unset variables keep their default values.

        :param prefix: environment variable name prefix.
        :return: wait configuration.
        :raises ValueError: if a variable's value cannot be parsed.
        """
        defaults = cls()
        timeout = _read_env_float(f"{prefix}TIMEOUT_SECONDS")
        sleep = _read_env_sleep_seconds(f"{prefix}SLEEP_SECONDS")
        max_attempts = _read_env_int(f"{prefix}MAX_ATTEMPTS")
        return cls(
            timeout_seconds=defaults.timeout_seconds if timeout is None else timeout,
            backoff=defaults.backoff if sleep is None else sleep,
            max_attempts=defaults.max_attempts if max_attempts is None else max_attempts,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class WaitOptions:
    """Parameters for one wait, extending the current configuration.

    ``None`` for the timeout and pause uses the ``WaitConfig`` values.
    ``UNSET`` for the attempt count uses the ``WaitConfig`` value.
    """

    timeout_seconds: float | None = None
    sleep_seconds: SleepSecondsType | Backoff | None = None
    max_attempts: MaxAttempts = UNSET
    message: str | None = None
    expected_exceptions: ExceptionsType = ()
    retry_on_exception: ExceptionFilter | None = None
    on_attempt: Callable[[Attempt], None] | None = None
    on_timeout: Callable[[Attempt], None] | None = None
    on_attempts_exhausted: Callable[[Attempt], None] | None = None


class _ConfigState:
    baseline = WaitConfig()
    lock = threading.RLock()


_override: ContextVar[WaitConfig | None] = ContextVar("explicit_wait_config", default=None)


def get_config() -> WaitConfig:
    """Get the current wait configuration.

    :return: temporary override from ``configured``, otherwise the process default.
    """
    override = _override.get()
    return _ConfigState.baseline if override is None else override


def configure(
    *,
    timeout_seconds: float | None = None,
    sleep_seconds: SleepSecondsType | Backoff | None = None,
    max_attempts: MaxAttempts = UNSET,
) -> WaitConfig:
    """Set defaults for all waits in the process.

    Omitted parameters keep their current values. Use ``configured`` for a temporary
    override within a test or code block.

    :param timeout_seconds: maximum wait time; ``math.inf`` waits forever.
    :param sleep_seconds: pause between attempts or a ``Backoff`` strategy.
    :param max_attempts: maximum number of attempts; None removes the limit,
        while omitting the argument keeps the current value.
    :return: applied configuration.
    :raises TypeError: if the time or attempt count has an invalid type.
    :raises ValueError: if numeric values are invalid.
    """
    with _ConfigState.lock:
        _ConfigState.baseline = _merge(
            _ConfigState.baseline,
            timeout_seconds,
            sleep_seconds,
            max_attempts,
        )
        return _ConfigState.baseline


def reset_config() -> WaitConfig:
    """Reset the wait configuration to its defaults.

    :return: default configuration.
    """
    with _ConfigState.lock:
        _ConfigState.baseline = WaitConfig()
        return _ConfigState.baseline


@contextmanager
def configured(
    *,
    timeout_seconds: float | None = None,
    sleep_seconds: SleepSecondsType | Backoff | None = None,
    max_attempts: MaxAttempts = UNSET,
) -> Iterator[WaitConfig]:
    """Temporarily override defaults within a block.

    The override applies in the current execution context, including coroutines,
    and is always removed on block exit, including on exceptions.

    :param timeout_seconds: maximum wait time; ``math.inf`` waits forever.
    :param sleep_seconds: pause between attempts or a ``Backoff`` strategy.
    :param max_attempts: maximum number of attempts; None removes the limit,
        while omitting the argument keeps the current value.
    :return: context manager yielding the applied configuration.
    :raises TypeError: if the time or attempt count has an invalid type.
    :raises ValueError: if numeric values are invalid.
    """
    config = _merge(get_config(), timeout_seconds, sleep_seconds, max_attempts)
    token = _override.set(config)
    try:
        yield config
    finally:
        _override.reset(token)


def _merge(
    config: WaitConfig,
    timeout_seconds: float | None,
    sleep_seconds: SleepSecondsType | Backoff | None,
    max_attempts: MaxAttempts,
) -> WaitConfig:
    return WaitConfig(
        timeout_seconds=config.timeout_seconds if timeout_seconds is None else timeout_seconds,
        backoff=config.backoff if sleep_seconds is None else Backoff.parse(sleep_seconds),
        max_attempts=config.max_attempts if max_attempts is UNSET else max_attempts,
    )


def _read_env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return _to_float(raw.strip(), name)


def _read_env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError as error:
        message = f"{name} must be an integer, got {raw!r}"
        raise ValueError(message) from error


def _read_env_sleep_seconds(name: str) -> Backoff | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    items = [item.strip() for item in raw.split(",")]
    if len(items) == 1:
        return Backoff(initial_seconds=_to_float(items[0], name))
    if len(items) > FULL_TUPLE_LENGTH:
        message = f"{name} must contain 1 to {FULL_TUPLE_LENGTH} numbers, got {raw!r}"
        raise ValueError(message)
    maximum = None if items[1].lower() in NONE_ALIASES else _to_float(items[1], name)
    multiplier = TUPLE_MULTIPLIER if len(items) == SHORT_TUPLE_LENGTH else _to_float(items[2], name)
    return Backoff(
        initial_seconds=_to_float(items[0], name),
        maximum_seconds=maximum,
        multiplier=multiplier,
    )


def _to_float(raw: str, name: str) -> float:
    try:
        return float(raw)
    except ValueError as error:
        message = f"{name} must contain numbers, got {raw!r}"
        raise ValueError(message) from error
