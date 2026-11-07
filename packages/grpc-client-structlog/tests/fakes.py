import logging
from typing import Protocol, cast

import structlog
from grpc_client_structlog.sink import REQUEST_EVENT, RESPONSE_EVENT, StructLogger
from structlog.stdlib import BoundLogger


class LogEntry:
    """Запись, попавшая в логгер."""

    def __init__(self, level: int, event: str, params: dict[str, object]) -> None:
        """Создать экземпляр с переданными настройками."""
        self.level = level
        self.event = event
        self.params = params

    def __repr__(self) -> str:
        return f"LogEntry(level={self.level}, event={self.event!r}, params={self.params!r})"


class LogMethod(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> None: ...


class CapturingSink:
    """Приемник записей structlog, который запоминает их вместо вывода.

    Заменяет собой логгер, который structlog создает фабрикой: bound-логгер вызывает у него
    метод по имени уровня и передает поля записи именованными аргументами.
    """

    def __init__(self, level: int) -> None:
        """Создать экземпляр с переданными настройками."""
        self.level = level
        self.calls: list[tuple[str, dict[str, object]]] = []

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802 — имя метода задано stdlib-логгером
        """Проверить, что записи указанного уровня доходят до вывода."""
        return level >= self.level

    def __getattr__(self, name: str) -> LogMethod:
        def record(*_args: object, **kwargs: object) -> None:
            self.calls.append((name, kwargs))

        return record


class StructlogRecorder:
    """Bound-логгер вместе с записями, которые он получил."""

    def __init__(self, logger: StructLogger, sink: CapturingSink) -> None:
        """Создать экземпляр с переданными настройками."""
        self.logger = logger
        self._sink = sink

    @property
    def entries(self) -> list[LogEntry]:
        """Все записи в порядке поступления."""
        levels = logging.getLevelNamesMapping()
        return [
            LogEntry(
                level=levels[method.upper()],
                event=str(params.get("event", "")),
                params={name: value for name, value in params.items() if name != "event"},
            )
            for method, params in self._sink.calls
        ]

    @property
    def requests(self) -> list[LogEntry]:
        """Записи об отправленных запросах."""
        return [entry for entry in self.entries if entry.event == REQUEST_EVENT]

    @property
    def responses(self) -> list[LogEntry]:
        """Записи о полученных ответах."""
        return [entry for entry in self.entries if entry.event == RESPONSE_EVENT]

    @property
    def request(self) -> LogEntry:
        """Запись о первом отправленном запросе."""
        return self.requests[0]

    @property
    def response(self) -> LogEntry:
        """Запись о первом полученном ответе."""
        return self.responses[0]


def build_stdlib_logger(level: int = logging.DEBUG) -> StructlogRecorder:
    """Собрать логгер так, как его собирает `structlog.configure(wrapper_class=BoundLogger)`.

    :param level: уровень, начиная с которого записи доходят до вывода
    :returns: логгер вместе с полученными им записями
    """
    sink = CapturingSink(level)
    context: dict[str, object] = {}
    return StructlogRecorder(BoundLogger(sink, [], context), sink)


class ExplodingSink(CapturingSink):
    """Приемник записей, у которого не работает проверка уровня.

    Так ведет себя связка `structlog.stdlib.BoundLogger` + `structlog.PrintLogger`: bound-логгер
    перекладывает вопрос об уровне на логгер под собой, а у `PrintLogger` отвечать на него нечем.
    """

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802, ARG002 — сигнатуру задает stdlib-логгер
        """Не ответить на вопрос об уровне так же, как это делает `PrintLogger`."""
        message = "'PrintLogger' object has no attribute 'isEnabledFor'"
        raise AttributeError(message)


def build_logger_with_broken_level_check() -> StructlogRecorder:
    """Собрать логгер, у которого падает проверка уровня, но запись работает.

    :returns: логгер вместе с полученными им записями
    """
    sink = ExplodingSink(logging.DEBUG)
    context: dict[str, object] = {}
    return StructlogRecorder(BoundLogger(sink, [], context), sink)


def build_filtering_logger(level: int = logging.DEBUG) -> StructlogRecorder:
    """Собрать логгер так, как его собирает `wrapper_class=make_filtering_bound_logger(...)`.

    Такой логгер и уронил gRPC-клиент: проверка уровня у него называется `is_enabled_for`,
    а не `isEnabledFor`.

    :param level: уровень, начиная с которого записи доходят до вывода
    :returns: логгер вместе с полученными им записями
    """
    sink = CapturingSink(level)
    logger = cast(
        "StructLogger",
        structlog.wrap_logger(sink, processors=[], wrapper_class=structlog.make_filtering_bound_logger(level)),
    )
    return StructlogRecorder(logger, sink)
