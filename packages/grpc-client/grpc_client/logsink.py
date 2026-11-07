import logging
from dataclasses import dataclass
from typing import Protocol

import grpc
from google.protobuf.message import Message

from .config import LOGGING_CONFIG
from .types import MetadataType
from .utils import logutils
from .utils.logutils import LogFormat


def resolve_log_levels(log_level: int | None = None, err_log_level: int | None = None) -> tuple[int, int]:
    """Подставить вместо `None` уровни из общей конфигурации.

    Нужна тем, кто должен знать итоговые уровни до сборки клиента — например, чтобы
    заранее отвергнуть уровень, которого не понимает вывод.

    :param log_level: уровень логирования успешных запросов
    :param err_log_level: уровень логирования запросов с ошибкой
    :return: пара уровней «успешный, с ошибкой»
    """
    return (
        log_level if log_level is not None else LOGGING_CONFIG.log_level,
        err_log_level if err_log_level is not None else LOGGING_CONFIG.err_log_level,
    )


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Отправленный gRPC-запрос."""

    # Идентификатор, связывающий запрос с ответом.
    trace_id: str

    # Полное имя вызываемого метода в виде /package.Service/Method.
    method: str

    # Отправляемое сообщение. `None`, когда телом запроса является поток сообщений.
    message: Message | None

    # Метаданные запроса.
    metadata: MetadataType | None


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    """Завершившийся gRPC вызов: успешный, с ошибкой либо законченный поток."""

    # Идентификатор, связывающий запрос с ответом.
    trace_id: str

    # Полное имя вызванного метода в виде /package.Service/Method.
    method: str

    # Итоговый код статуса вызова.
    status_code: grpc.StatusCode

    # Ответное сообщение. `None` у потоковых ответов и у вызовов с ошибкой.
    message: Message | None

    # Текст ошибки от сервиса. Пустая строка, когда вызов успешен.
    details: str

    # Метаданные ответа.
    metadata: MetadataType | None

    # Количество полученных сообщений. `None` у унарных ответов.
    messages_count: int | None

    @property
    def succeeded(self) -> bool:
        """Признак успешно завершившегося вызова."""
        return self.status_code is grpc.StatusCode.OK

    @property
    def is_stream(self) -> bool:
        """Признак того, что запись описывает завершившийся поток ответов."""
        return self.messages_count is not None


class LogSink(Protocol):
    """Приемник записей о gRPC вызовах.

    Интерцептор собирает записи и выбирает уровень, приемник решает, куда и в каком виде
    они попадут. Реализация подключается опцией `options.with_log_sink`.

    Требования к реализации:

    - методы приходят из разных потоков — финальный лог потока ответов пишется из служебного
      потока канала grpcio, а асинхронный лог из задачи событийного цикла;
    - долгая работа внутри метода задерживает сам вызов: запись запроса делается до отправки;
    - исключение приемника интерцептор гасит и вызов не срывает, но запись при этом теряется.
    """

    def is_enabled_for(self, level: int) -> bool:
        """Проверить, что записи указанного уровня дойдут до вывода.

        Интерцептор спрашивает об этом до сборки записи: подготовка тела сообщения стоит
        дороже самого вопроса. Когда оба уровня выключены, интерцептор не делает вообще
        ничего — не создает идентификатор и не оборачивает поток ради подсчета сообщений.

        :param level: уровень записи
        :return: True, если запись такого уровня дойдет до вывода
        """
        ...

    def write_request(self, level: int, record: RequestRecord) -> None:
        """Записать отправленный запрос.

        :param level: уровень записи
        :param record: данные запроса
        """
        ...

    def write_response(self, level: int, record: ResponseRecord) -> None:
        """Записать завершившийся вызов.

        :param level: уровень записи
        :param record: данные завершившегося вызова
        """
        ...


class TextLogSink:
    """Приемник, пишущий записи одной строкой в логгер stdlib."""

    def __init__(self, logger: logging.Logger, log_format: LogFormat | None = None) -> None:
        """Инициализатор.

        :param logger: логгер, в который пишутся запросы и ответы
        :param log_format: правила оформления лога, по умолчанию из общей конфигурации
        """
        self._logger = logger
        self._format = log_format if log_format is not None else LogFormat.from_config()

    def is_enabled_for(self, level: int) -> bool:
        """Проверить, что логгер пишет записи указанного уровня."""
        return self._logger.isEnabledFor(level)

    def write_request(self, level: int, record: RequestRecord) -> None:
        """Записать отправленный запрос."""
        self._logger.log(
            level,
            logutils.request_log(
                trace_id=record.trace_id,
                method=record.method,
                message=record.message,
                metadata=record.metadata,
                log_format=self._format,
            ),
        )

    def write_response(self, level: int, record: ResponseRecord) -> None:
        """Записать завершившийся вызов."""
        self._logger.log(level, self._response_text(record))

    def _response_text(self, record: ResponseRecord) -> str:
        """Собрать строку лога, подходящую исходу вызова."""
        if not record.succeeded:
            return logutils.error_log(
                trace_id=record.trace_id,
                method=record.method,
                status_code=record.status_code,
                details=record.details,
                metadata=record.metadata,
                log_format=self._format,
            )

        if record.messages_count is not None:
            return logutils.stream_response_log(
                trace_id=record.trace_id,
                method=record.method,
                status_code=record.status_code,
                messages_count=record.messages_count,
                metadata=record.metadata,
                log_format=self._format,
            )

        return logutils.response_log(
            trace_id=record.trace_id,
            method=record.method,
            status_code=record.status_code,
            message=record.message,
            metadata=record.metadata,
            log_format=self._format,
        )
