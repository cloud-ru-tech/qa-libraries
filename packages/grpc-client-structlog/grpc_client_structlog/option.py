from collections.abc import Sequence
from typing import TypedDict, Unpack

from grpc_client import BaseGRPCClient, ClientOption, options, resolve_log_levels
from grpc_client.utils.logutils import LogFormat

from .sink import StructLogger, StructlogSink, check_supported_level


class StructLoggerOptions(TypedDict, total=False):
    """Structured logging options."""

    sanitize_keys: Sequence[str] | None
    json_indent: int | None
    log_level: int | None
    err_log_level: int | None
    payload_maxlength: int | None
    use_default_sanitize_keys: bool


def with_structlogger(logger: StructLogger, **settings: Unpack[StructLoggerOptions]) -> ClientOption:
    """Set a structured logger for gRPC client requests and responses.

    :param logger: structured logger
    :param sanitize_keys: metadata key names and paths in the format
                          [glom](https://glom.readthedocs.io/en/latest/) in the message body,
                          whose values should be hidden
    :param json_indent: indentation width for JSON property logging (defaults to no indentation)
    :param log_level: gRPC client logging level, defaults to INFO;
                      structlog accepts only DEBUG, INFO, WARNING, ERROR, and CRITICAL
    :param err_log_level: failed request logging level, defaults to ERROR;
                          the allowed values are the same
    :param payload_maxlength: maximum logged message body length, defaults to 4096 characters;
                              `None` in `grpc_client.configure_logging` removes the limit
    :param use_default_sanitize_keys: whether to hide fields with common secret names
                                      (see `grpc_client.utils.sanitizer.DEFAULT_SANITIZE_KEYS`)
                                      at any depth, in addition to `sanitize_keys`
    :returns: option applied to a gRPC client to set its logger
    :raises ValueError: when building the client if structlog does not support the logging level
    """

    def option(client: BaseGRPCClient[object]) -> None:
        # Read shared settings when building the client rather than creating the option:
        # `grpc_client.configure_logging` may have been called after the option was created.
        levels = resolve_log_levels(settings.get("log_level"), settings.get("err_log_level"))
        # Check the resolved level: unsupported values can come
        # both from an argument and from `configure_logging`.
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
