from collections.abc import Sequence
from typing import TypedDict, Unpack

from grpc_client import BaseGRPCClient, ClientOption, options, resolve_log_levels
from grpc_client.utils.logutils import LogFormat

from .sink import StructLogger, StructlogSink, check_supported_level


class StructLoggerOptions(TypedDict, total=False):
    """Параметры структурированного логирования."""

    sanitize_keys: Sequence[str] | None
    json_indent: int | None
    log_level: int | None
    err_log_level: int | None
    payload_maxlength: int | None
    use_default_sanitize_keys: bool


def with_structlogger(logger: StructLogger, **settings: Unpack[StructLoggerOptions]) -> ClientOption:
    """Установить структурированный логгер для логирования запросов и ответов в gRPC-клиенте.

    :param logger: структурированный логгер
    :param sanitize_keys: имена ключей метаданных и пути в формате
                          [glom](https://glom.readthedocs.io/en/latest/) в теле сообщения,
                          значения которых нужно скрыть
    :param json_indent: ширина отступа для логирования JSON свойств (по умолчанию отступ отсутствует)
    :param log_level: уровень логов gRPC-клиента, по умолчанию INFO;
                      structlog принимает только DEBUG, INFO, WARNING, ERROR и CRITICAL
    :param err_log_level: уровень логов запросов, завершившихся ошибкой, по умолчанию ERROR;
                          набор допустимых значений тот же
    :param payload_maxlength: максимальная длина тела сообщения в логе, по умолчанию 4096 символов;
                              `None` в `grpc_client.configure_logging` снимает ограничение
    :param use_default_sanitize_keys: скрывать ли поля с типовыми именами секретов
                                      (см. `grpc_client.utils.sanitizer.DEFAULT_SANITIZE_KEYS`)
                                      на любой глубине, в дополнение к `sanitize_keys`
    :returns: опция, которая применяется к gRPC-клиенту для установки логгера
    :raises ValueError: при сборке клиента, если уровень логирования не поддерживается structlog
    """

    def option(client: BaseGRPCClient[object]) -> None:
        # Общая настройка читается в момент сборки клиента, а не создания опции:
        # `grpc_client.configure_logging` могли вызвать уже после того, как опцию создали.
        levels = resolve_log_levels(settings.get("log_level"), settings.get("err_log_level"))
        # Проверяется уже подставленный уровень: неподдерживаемое значение приходит
        # и аргументом, и из `configure_logging`.
        check_supported_level("log_level", levels[0])
        check_supported_level("err_log_level", levels[1])

        sink = StructlogSink(
            logger=logger,
            log_format=LogFormat.from_config(
                sanitize_keys=settings.get("sanitize_keys"),
                json_indent=settings.get("json_indent"),
                payload_maxlength=settings.get("payload_maxlength"),
                use_default_sanitize_keys=settings.get("use_default_sanitize_keys", True),
            ),
        )
        options.with_log_sink(sink, log_level=levels[0], err_log_level=levels[1])(client)

    return option
