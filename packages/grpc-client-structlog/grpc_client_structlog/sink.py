import logging

import grpc
from grpc_client import RequestRecord, ResponseRecord
from grpc_client.utils.logutils import LogFormat
from structlog.stdlib import BoundLogger
from structlog.typing import FilteringBoundLogger

from .parser import parse_error, parse_request, parse_response, parse_stream_response

# Bound-логгер structlog: стандартный поверх stdlib либо класс из `make_filtering_bound_logger`.
# Второй не подходит под первый: у него другое написание методов проверки уровня.
StructLogger = BoundLogger | FilteringBoundLogger

# Событие отправленного запроса.
REQUEST_EVENT = "grpc request sent"

# Событие полученного ответа: и успешного, и с ошибкой, и завершения потока.
RESPONSE_EVENT = "grpc response received"

# Уровни, которыми умеет писать structlog.
#
# stdlib-логгер принимает любое число, а bound-логгер structlog выбирает метод по имени уровня,
# и имена есть только у этих пяти. Промежуточное значение вроде 15 stdlib-логгер записал бы,
# а structlog роняет с `KeyError`.
SUPPORTED_LOG_LEVELS = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)


class StructlogSink:
    """Приемник, пишущий записи о gRPC вызовах в structlog отдельными полями."""

    def __init__(self, logger: StructLogger, log_format: LogFormat | None = None) -> None:
        """Инициализатор.

        :param logger: структурированный логгер, в который пишутся запросы и ответы
        :param log_format: правила оформления лога, по умолчанию из общей конфигурации
        """
        self._logger = logger
        self._format = log_format if log_format is not None else LogFormat.from_config()

    def is_enabled_for(self, level: int) -> bool:
        """Проверить, что логгер пишет записи указанного уровня.

        Проверка может не ответить: класс bound-логгера задает пользователь в `structlog.configure`,
        и, например, `structlog.stdlib.BoundLogger` перекладывает вопрос на логгер под собой,
        а у `structlog.PrintLogger` отвечать на него нечем. Такой логгер считается пишущим:
        молча потерять записи хуже, чем собрать лишнюю, а ронять из-за вопроса об уровне сам
        вызов нельзя тем более.

        :param level: уровень записи
        :returns: True, если запись такого уровня дойдет до вывода
        """
        try:
            return self._logger.is_enabled_for(level)
        except Exception:  # noqa: BLE001 — нерабочая проверка не должна ломать вызов
            return True

    def write_request(self, level: int, record: RequestRecord) -> None:
        """Записать отправленный запрос."""
        self._write(level, REQUEST_EVENT, parse_request(record, self._format))

    def write_response(self, level: int, record: ResponseRecord) -> None:
        """Записать завершившийся вызов."""
        self._write(level, RESPONSE_EVENT, self._response_properties(record))

    def _response_properties(self, record: ResponseRecord) -> dict[str, object]:
        """Собрать поля лога, подходящие исходу вызова."""
        if record.status_code is not grpc.StatusCode.OK:
            return parse_error(record, self._format)
        if record.messages_count is not None:
            return parse_stream_response(record, self._format)
        return parse_response(record, self._format)

    def _write(self, level: int, event: str, properties: dict[str, object]) -> None:
        """Записать событие с полями в структурированный логгер."""
        self._logger.log(level, event, **properties)


def check_supported_level(name: str, level: int) -> None:
    """Проверить, что structlog умеет писать таким уровнем.

    Проверка делается на сборке клиента, а не на первом запросе: иначе опечатка в настройке
    уровня превращается в `KeyError` из недр structlog, и запрос при этом даже не уходит —
    запись о нем строится до вызова.

    :param name: имя параметра, в котором пришел уровень
    :param level: проверяемый уровень
    :raises ValueError: если уровень не из `SUPPORTED_LOG_LEVELS`
    """
    if level in SUPPORTED_LOG_LEVELS:
        return

    supported = ", ".join(f"{logging.getLevelName(value)} ({value})" for value in SUPPORTED_LOG_LEVELS)
    message = f"structlog не умеет писать уровнем {level}: {name} принимает только {supported}"
    raise ValueError(message)
