from collections.abc import Sequence

from http_client import AsyncHttpClient, BaseHttpClient, ClientOption
from http_client.event_hooks import DEFAULT_SANITIZE_KEYS
from structlog.stdlib import BoundLogger

from .event_hooks import async_response_logger_hook, request_logger_hook, response_logger_hook
from .sanitizer import Sanitizer


def with_structlogger(
    logger: BoundLogger,
    sanitize_keys: Sequence[str] | None = None,
    json_indent: int | None = None,
    log_level: int | None = None,
    *,
    use_default_sanitize_keys: bool = True,
) -> ClientOption:
    """Установить структурированный логгер для логирования запросов и ответов в HTTP-клиенте.

    :param logger: структурированный логгер
    :param sanitize_keys: пути в формате [glom](https://glom.readthedocs.io/en/latest/)
                          к полям, которые нужно скрыть
    :param json_indent: ширина отступа для логирования JSON свойств (по умолчанию отступ отсутствует)
    :param log_level: уровень логов HTTP-клиент, по умолчанию INFO
    :param use_default_sanitize_keys: скрывать ли поля с типовыми именами секретов
                                      (см. `http_client.event_hooks.DEFAULT_SANITIZE_KEYS`)
                                      на любой глубине, в дополнение к `sanitize_keys`
    :returns: опция, которая применяется к HTTP-клиенту для установки логгера и хуков
    """
    sanitizer = Sanitizer(
        glom_paths=sanitize_keys or (),
        secret_names=DEFAULT_SANITIZE_KEYS if use_default_sanitize_keys else (),
    )

    def option(client: BaseHttpClient) -> None:
        client.add_request_hook(
            request_logger_hook(
                logger=logger,
                sanitizer=sanitizer,
                json_indent=json_indent,
                log_level=log_level,
            )
        )

        build_response_hook = (
            async_response_logger_hook if isinstance(client, AsyncHttpClient) else response_logger_hook
        )
        client.add_response_hook(
            build_response_hook(
                logger=logger,
                sanitizer=sanitizer,
                json_indent=json_indent,
                log_level=log_level,
            )
        )

    return option
