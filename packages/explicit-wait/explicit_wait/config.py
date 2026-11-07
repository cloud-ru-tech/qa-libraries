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
    """Значения по умолчанию для функций ожидания.

    Объект неизменяемый: заменить настройки можно только целиком, поэтому «полуприменённое»
    состояние из двух несогласованных полей невозможно.
    """

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    backoff: Backoff = DEFAULT_BACKOFF
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        """Проверить корректность значений конфигурации.

        :raises TypeError: если время или число попыток имеют неверный тип.
        :raises ValueError: если значения выходят за допустимые границы.
        """
        validate_timeout_seconds(self.timeout_seconds)
        validate_max_attempts(self.max_attempts)

    @classmethod
    def from_env(cls, prefix: str = ENV_PREFIX) -> "WaitConfig":
        """Собрать конфигурацию из переменных окружения.

        Читает ``<prefix>TIMEOUT_SECONDS``, ``<prefix>SLEEP_SECONDS`` и
        ``<prefix>MAX_ATTEMPTS``. Пауза задаётся числом (``1.5``) либо перечислением через
        запятую (``2,64`` или ``2,64,3``); ``none`` в позиции максимума снимает ограничение.
        Незаданные переменные оставляют значение по умолчанию.

        :param prefix: префикс имён переменных окружения.
        :return: конфигурация ожиданий.
        :raises ValueError: если значение переменной нельзя разобрать.
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
    """Параметры одного ожидания, дополняющие действующую конфигурацию.

    ``None`` у времени и паузы использует значения ``WaitConfig``.
    ``UNSET`` у числа попыток использует значение ``WaitConfig``.
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
    """Получить действующую конфигурацию ожиданий.

    :return: временное переопределение из ``configured``, иначе процессный дефолт.
    """
    override = _override.get()
    return _ConfigState.baseline if override is None else override


def configure(
    *,
    timeout_seconds: float | None = None,
    sleep_seconds: SleepSecondsType | Backoff | None = None,
    max_attempts: MaxAttempts = UNSET,
) -> WaitConfig:
    """Задать значения по умолчанию для всех ожиданий в процессе.

    Незаданные параметры сохраняют текущие значения. Для временного переопределения
    в рамках теста или блока кода используйте ``configured``.

    :param timeout_seconds: максимальное время ожидания; ``math.inf`` — ждать бесконечно.
    :param sleep_seconds: пауза между попытками или стратегия ``Backoff``.
    :param max_attempts: максимальное число попыток; None снимает ограничение,
        пропущенный аргумент сохраняет текущее значение.
    :return: применённая конфигурация.
    :raises TypeError: если время или число попыток имеют неверный тип.
    :raises ValueError: если числовые значения некорректны.
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
    """Вернуть конфигурацию ожиданий к значениям по умолчанию.

    :return: конфигурация по умолчанию.
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
    """Временно переопределить значения по умолчанию внутри блока.

    Переопределение действует в текущем контексте выполнения, включая корутины, и
    гарантированно снимается при выходе из блока, в том числе при исключении.

    :param timeout_seconds: максимальное время ожидания; ``math.inf`` — ждать бесконечно.
    :param sleep_seconds: пауза между попытками или стратегия ``Backoff``.
    :param max_attempts: максимальное число попыток; None снимает ограничение,
        пропущенный аргумент сохраняет текущее значение.
    :return: контекстный менеджер, отдающий применённую конфигурацию.
    :raises TypeError: если время или число попыток имеют неверный тип.
    :raises ValueError: если числовые значения некорректны.
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
