import json
import logging
import os
from collections.abc import Generator, Sequence
from pathlib import Path, PurePath, PureWindowsPath
from typing import Final, Protocol, cast

import pytest

from . import hooks
from .handler import HandlerOptions, LoggingContextHandler
from .naming import build_test_id, build_test_name, params_of

# Имя самого модуля плагина занято entry point'ом, поэтому экземпляр
# регистрируется под отдельным именем.
PLUGIN_NAME: Final = "logging_context_runtime"

_LOGGER_NAME: Final = "logging_context"

DEFAULT_FORMAT: Final = "%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT: Final = "%d.%m.%Y %H:%M:%S"
DEFAULT_LEVEL: Final = "INFO"

LAUNCH_ID_OPTION: Final = "--logging-context-launch-id"
LAUNCH_ID_ENV: Final = "LOGGING_CONTEXT_LAUNCH_ID"
LAUNCH_ID_INI: Final = "logging_context_launch_id"

_LAUNCH_ID_DEST: Final = "logging_context_launch_id"
_NO_INDENT: Final = -1
_CONTROLLER_ID: Final = "master"


class _AttachmentTypes(Protocol):
    TEXT: object


class _Allure(Protocol):
    attachment_type: _AttachmentTypes

    def attach(self, body: str, *, name: str, attachment_type: object) -> None: ...


class _HookDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


_WRAPPER = cast("_HookDecorator", pytest.hookimpl(wrapper=True))
_INNER_WRAPPER = cast("_HookDecorator", pytest.hookimpl(wrapper=True, trylast=True))
_FIRST = cast("_HookDecorator", pytest.hookimpl(tryfirst=True))


class _ConfigureHook(Protocol):
    def __call__(self, *, handler: LoggingContextHandler, config: pytest.Config) -> object: ...


allure: _Allure | None
try:
    import allure as _allure
except ImportError:  # pragma: no cover - allure необязателен
    allure = None
else:
    allure = cast("_Allure", _allure)


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    """Зарегистрировать точки расширения.

    :param pluginmanager: объект конфигурации pytest.
    """
    pluginmanager.add_hookspecs(hooks)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Зарегистрировать настройки плагина.

    :param parser: объект конфигурации pytest.
    """
    parser.addoption(
        LAUNCH_ID_OPTION,
        action="store",
        dest=_LAUNCH_ID_DEST,
        default=None,
        metavar="ID",
        help=(
            f"Идентификатор запуска: подкаталог внутри logging_context_dir. "
            f"Приоритет: эта опция, затем {LAUNCH_ID_ENV}, затем {LAUNCH_ID_INI} из ini."
        ),
    )
    parser.addini(
        "logging_context_dir",
        "Каталог для файлов логов. Пока не задан, плагин не активен. Относительный путь считается от rootdir.",
        default="",
    )
    parser.addini(
        LAUNCH_ID_INI,
        f"Идентификатор запуска: подкаталог внутри logging_context_dir. "
        f"Переопределяется опцией {LAUNCH_ID_OPTION} и переменной {LAUNCH_ID_ENV}.",
        default="",
    )
    parser.addini(
        "logging_context_loggers",
        "Логгеры, с которых собирать записи. По умолчанию — root, то есть всё.",
        type="args",
        default=list[str](),
    )
    parser.addini(
        "logging_context_level",
        "Минимальный уровень записей.",
        default=DEFAULT_LEVEL,
    )
    parser.addini(
        "logging_context_format",
        "Формат строки лога.",
        default=DEFAULT_FORMAT,
    )
    parser.addini(
        "logging_context_date_format",
        "Формат времени в логах.",
        default=DEFAULT_DATE_FORMAT,
    )
    parser.addini(
        "logging_context_attach_allure",
        "Прикреплять файлы логов к allure-отчёту.",
        type="bool",
        default=True,
    )
    parser.addini(
        "logging_context_attach_fixtures_log",
        "Прикреплять общий файл логов фикстур к каждому тесту.",
        type="bool",
        default=True,
    )
    parser.addini(
        "logging_context_log_test_header",
        "Писать в начало файла строку с идентификатором и параметрами теста.",
        type="bool",
        default=True,
    )
    parser.addini(
        "logging_context_params_indent",
        "Отступ при сериализации параметров теста в JSON. -1 — в одну строку.",
        type="int",
        default=_NO_INDENT,
    )


def pytest_configure(config: pytest.Config) -> None:
    """Создать хендлер и подключить плагин.

    :param config: объект конфигурации pytest.
    """
    output_dir = _resolve_output_dir(config)
    if output_dir is None:
        return

    worker_id = _worker_id(config)
    handler = LoggingContextHandler(
        output_dir,
        f"fixtures_{worker_id}.log",
        # Под xdist воркеры делят каталог, поэтому имя файла должно быть
        # различимым между процессами.
        options=HandlerOptions(name_suffix="" if worker_id == _CONTROLLER_ID else worker_id),
    )
    handler.setLevel(_resolve_level(cast("str", config.getini("logging_context_level"))))
    handler.setFormatter(
        logging.Formatter(
            fmt=str(cast("str", config.getini("logging_context_format"))),
            datefmt=str(cast("str", config.getini("logging_context_date_format"))),
        ),
    )

    plugin = LoggingContextPlugin(config, handler)
    config.pluginmanager.register(plugin, PLUGIN_NAME)
    cast("_ConfigureHook", config.hook.pytest_logging_context_configure)(handler=handler, config=config)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Закрыть хендлер и отключить плагин.

    :param config: объект конфигурации pytest.
    """
    plugin = cast("object", config.pluginmanager.get_plugin(PLUGIN_NAME))
    if isinstance(plugin, LoggingContextPlugin):
        plugin.shutdown()
        config.pluginmanager.unregister(plugin)


class LoggingContextPlugin:
    """Переключает файл логов на каждый тест и прикрепляет их к allure."""

    def __init__(self, config: pytest.Config, handler: LoggingContextHandler) -> None:
        """Инициализировать объект.

        :param config: значение настройки ``config``.
        :param handler: значение настройки ``handler``.
        """
        self._handler = handler
        self._attach_allure = bool(cast("bool", config.getini("logging_context_attach_allure")))
        self._attach_fixtures_log = bool(cast("bool", config.getini("logging_context_attach_fixtures_log")))
        self._log_test_header = bool(cast("bool", config.getini("logging_context_log_test_header")))

        indent = int(cast("int", config.getini("logging_context_params_indent")))
        self._params_indent = None if indent == _NO_INDENT else indent

        self._item: pytest.Item | None = None
        self._logger_names: list[str] = [
            str(name) for name in cast("list[str]", config.getini("logging_context_loggers"))
        ]
        self._targets = _LoggerTargets(handler, self._logger_names)
        self._targets.attach()

    @property
    def handler(self) -> LoggingContextHandler:
        """Хендлер, которым плагин пишет логи."""
        return self._handler

    @_WRAPPER
    def pytest_runtest_protocol(self, item: pytest.Item) -> Generator[None, object, object]:
        """Запоминает тест, чтобы его имя было доступно в хуках попытки."""
        self._item = item
        try:
            return (yield)
        finally:
            self._item = None

    def pytest_runtest_logstart(self) -> None:
        """Привязывает файл на каждую попытку теста.

        Вызывается заново на каждый rerun, поэтому попытки не смешиваются
        в одном файле. Покрывает setup и teardown всех фикстур попытки.
        """
        if self._item is None:
            return

        # Плагины вроде pytest-rerunfailures вызывают хук на каждую попытку.
        # Отвязываем на всякий случай, чтобы повторный вызов не ронял прогон.
        self._handler.unbind()
        self._targets.attach_late_loggers()
        self._handler.bind(build_test_name(self._item))

    def pytest_runtest_logfinish(self) -> None:
        """Возвращает логи в общий файл после попытки."""
        self._handler.unbind()

    # trylast делает обёртку самой внутренней: код после yield выполняется,
    # когда все финализаторы теста уже отработали, но контекст allure ещё
    # открыт — только в этот момент вложение попадёт в нужный тест.
    @_INNER_WRAPPER
    def pytest_runtest_teardown(self) -> Generator[None, object, object]:
        """Прикрепляет логи к allure после того, как отработали все фикстуры."""
        try:
            return (yield)
        finally:
            self._attach_to_allure()

    @_FIRST
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Пишет в начало файла идентификатор теста и его параметры."""
        if not self._log_test_header:
            return

        test_id = build_test_id(item)
        params = params_of(item)

        if params:
            # json.dumps намеренно не защищён try/except: несериализуемые
            # параметры должны приводить к setup error, а не молча теряться.
            rendered = json.dumps(
                params,
                ensure_ascii=False,
                default=str,
                indent=self._params_indent,
            )
            message = f"Запуск теста id={test_id} с параметрами {rendered}"
        else:
            message = f"Запуск теста id={test_id}"

        self._emit_directly(message)

    def _attach_to_allure(self) -> None:
        """Прикрепить файл логов текущего теста (и файл фикстур) к отчёту."""
        if not self._attach_allure or allure is None:
            return

        self._handler.flush()

        current = self._handler.current_file
        if current is not None:
            self._attach_file(current)

        if self._attach_fixtures_log:
            self._attach_file(self._handler.fixtures_file)

    def shutdown(self) -> None:
        """Снять хендлер с логгеров, вернуть их уровни и закрыть файлы."""
        self._targets.detach()
        self._handler.close()

    def _emit_directly(self, message: str) -> None:
        """Отправить служебную запись прямо в хендлер.

        Минуя дерево логгеров — иначе заголовок терялся бы при
        `logging_context_loggers`, суженном до пользовательских логгеров.
        """
        record = logging.LogRecord(
            name=_LOGGER_NAME,
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        self._handler.handle(record)

    @staticmethod
    def _attach_file(path: Path) -> None:
        if allure is None or not path.exists():
            return

        content = path.read_text(encoding="utf-8", errors="backslashreplace")
        if not content:
            return

        allure.attach(
            content,
            name=path.name,
            attachment_type=allure.attachment_type.TEXT,
        )


def _resolve_output_dir(config: pytest.Config) -> Path | None:
    """Каталог для логов или None, если плагин не активирован."""
    configured = str(cast("str", config.getini("logging_context_dir")))
    if not configured:
        return None

    output_dir = Path(configured)
    if not output_dir.is_absolute():
        # Относительно rootdir, а не cwd: cwd может поменяться во время прогона.
        output_dir = config.rootpath / output_dir

    launch_id = _validate_path_component(*_launch_id(config))
    return output_dir / launch_id if launch_id else output_dir


def _launch_id(config: pytest.Config) -> tuple[str, str]:
    """Идентификатор запуска и источник, из которого он взят."""
    from_option = cast("str | None", config.getoption(_LAUNCH_ID_DEST, default=""))
    if from_option:
        return str(from_option), LAUNCH_ID_OPTION

    from_env = os.environ.get(LAUNCH_ID_ENV)
    if from_env:
        return from_env, LAUNCH_ID_ENV

    return str(cast("str", config.getini(LAUNCH_ID_INI))), LAUNCH_ID_INI


def _worker_id(config: pytest.Config) -> str:
    """Идентификатор воркера pytest-xdist или «master» при обычном запуске."""
    workerinput = cast("dict[str, object] | None", getattr(config, "workerinput", None))
    if workerinput is None:
        return "master"

    return str(workerinput.get("workerid", "master"))


def _validate_path_component(value: str, source: str) -> str:
    """Проверить, что значение — один безопасный компонент пути."""
    if not value:
        return value

    is_unsafe = (
        value in {".", ".."}
        or any(char in value for char in ("/", "\\", "\0"))
        or PurePath(value).is_absolute()
        # «D:run» не абсолютный и без разделителей, но на Windows уводит на
        # другой диск: output_dir / "D:run" даёт "D:run".
        or bool(PureWindowsPath(value).drive)
    )
    if is_unsafe:
        message = (
            f"{source}={value!r} must be a single path component: no «/», «\\», NUL, «.», «..», "
            f"no drive letter and not an absolute path"
        )
        raise pytest.UsageError(message)

    return value


def _resolve_level(value: str) -> int:
    """Уровень логирования из имени («DEBUG») или числа («10»)."""
    if value.isdigit():
        return int(value)

    level = logging.getLevelNamesMapping().get(value.upper())
    if level is None:
        message = f"logging_context_level={value!r} is not a valid logging level"
        raise pytest.UsageError(message)

    return level


class _LoggerTargets:
    """Логгеры, на которых висит хендлер, с их исходными уровнями."""

    def __init__(self, handler: LoggingContextHandler, logger_names: Sequence[str]) -> None:
        """Инициализировать объект.

        :param handler: значение настройки ``handler``.
        :param logger_names: значение настройки ``logger_names``.
        """
        self._handler = handler
        self._names = list(logger_names)
        self._original_levels: dict[logging.Logger, int] = {}

    def attach(self) -> None:
        """Повесить хендлер на указанные логгеры либо на root."""
        if self._names:
            self._attach_all(_without_descendants([logging.getLogger(name) for name in self._names]))
            return

        root = logging.getLogger()
        self._attach_all([root, *_non_propagating_loggers(root)])

    def attach_late_loggers(self) -> None:
        """Догнать логгеры с `propagate=False`, созданные после старта прогона.

        Такие логгеры не доходят до root, а на момент `pytest_configure` их
        ещё не существовало: тестовые модули импортируются позже.
        """
        if self._names:
            return

        self._attach_all(_non_propagating_loggers(logging.getLogger()))

    def detach(self) -> None:
        """Снять хендлер и вернуть логгерам исходные уровни."""
        for logger, level in self._original_levels.items():
            logger.removeHandler(self._handler)
            logger.setLevel(level)
        self._original_levels.clear()

    def _attach_all(self, loggers: Sequence[logging.Logger]) -> None:
        level = self._handler.level
        for logger in loggers:
            if logger in self._original_levels:
                continue

            self._original_levels[logger] = logger.level
            logger.addHandler(self._handler)
            if logger.level == logging.NOTSET or logger.level > level:
                logger.setLevel(level)


def _without_descendants(loggers: Sequence[logging.Logger]) -> list[logging.Logger]:
    """Убрать логгеры, чьи записи и так дойдут до выбранного предка.

    Иначе хендлер, повешенный и на `app`, и на `app.http`, обработает одну
    запись дважды и продублирует строку в файле.
    """
    selected = {logger.name for logger in loggers}
    return [logger for logger in loggers if not _has_selected_ancestor(logger, selected)]


def _has_selected_ancestor(logger: logging.Logger, selected: set[str]) -> bool:
    parent = logger.parent
    while parent is not None:
        if not logger.propagate:
            return False
        if parent.name in selected:
            return True
        if not parent.propagate:
            return False
        logger, parent = parent, parent.parent

    return False


def _non_propagating_loggers(root: logging.Logger) -> list[logging.Logger]:
    return [
        logger
        for logger in list(root.manager.loggerDict.values())
        if isinstance(logger, logging.Logger) and not logger.propagate and logger is not root
    ]
