import inspect
from logging import Logger
from typing import Unpack, cast

import grpc

from .async_client import AsyncGRPCClient
from .base_client import BaseGRPCClient, ClientOption
from .interceptors import (
    AsyncAuthInterceptor,
    AsyncAutogenerateRequestIdInterceptor,
    AsyncAutogenerateTraceparentInterceptor,
    AsyncLoggingInterceptor,
    AuthInterceptor,
    AutogenerateRequestIdInterceptor,
    AutogenerateTraceparentInterceptor,
    LoggingInterceptor,
)
from .logsink import LogSink
from .metadata import merge_metadata
from .types import AsyncClientAuth, ChannelOptions, ClientAuth, MetadataType
from .utils.logutils import LoggerOptions


def with_timeout(timeout: float | None) -> ClientOption:
    """Установить ограничение времени вызова по умолчанию.

    :param timeout: время в секундах; `None` — без ограничения
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.timeout = timeout

    return option


def with_insecure_channel() -> ClientOption:
    """Использовать незашифрованный канал.

    Передаваемые данные, включая токены авторизации, не защищены. Допустимо только
    для локальной отладки и тестовых стендов.

    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.secure = False

    return option


def with_ssl_credentials(credentials: grpc.ChannelCredentials) -> ClientOption:
    """Установить учетные данные TLS для канала.

    :param credentials: учетные данные канала, например с корпоративным корневым сертификатом
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.secure = True
        client.ssl_credentials = credentials

    return option


def with_root_certificates(root_certificates: bytes) -> ClientOption:
    """Использовать переданный корневой сертификат для проверки сервера.

    :param root_certificates: содержимое PEM-файла с корневым сертификатом
    :return: опция клиента
    """
    return with_ssl_credentials(grpc.ssl_channel_credentials(root_certificates=root_certificates))


def with_channel_options(options: ChannelOptions) -> ClientOption:
    """Установить низкоуровневые настройки канала grpcio.

    Здесь же настраиваются встроенные повторы через `grpc.service_config`.

    :param options: пары «имя настройки — значение»
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.channel_options = tuple(options)

    return option


def with_compression(compression: grpc.Compression) -> ClientOption:
    """Установить алгоритм сжатия сообщений.

    :param compression: алгоритм сжатия
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.compression = compression

    return option


def with_default_metadata(metadata: MetadataType) -> ClientOption:
    """Добавлять метаданные к каждому запросу клиента.

    :param metadata: метаданные, добавляемые к каждому запросу
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.default_metadata = merge_metadata(client.default_metadata, metadata)

    return option


def with_interceptor(*interceptors: object) -> ClientOption:
    """Добавить интерцепторы к клиенту.

    Порядок важен: интерцепторы применяются в порядке добавления, поэтому логирующий
    интерцептор стоит добавлять после авторизующего, чтобы в лог попал итоговый запрос.

    :param interceptors: интерцепторы grpcio, синхронные либо асинхронные
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        for interceptor in interceptors:
            _add_interceptor(client, interceptor)

    return option


def with_auth(auth: ClientAuth | AsyncClientAuth, *, retry_on_unauthenticated: bool = True) -> ClientOption:
    """Подставлять токен доступа в каждый запрос клиента.

    :param auth: источник токена доступа
    :param retry_on_unauthenticated: повторять ли унарный запрос с новым токеном после UNAUTHENTICATED
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        interceptor: object
        if isinstance(client, AsyncGRPCClient):
            interceptor = AsyncAuthInterceptor(
                auth=_as_async_auth(auth),
                retry_on_unauthenticated=retry_on_unauthenticated,
            )
        else:
            interceptor = AuthInterceptor(
                auth=_as_sync_auth(auth),
                retry_on_unauthenticated=retry_on_unauthenticated,
            )
        _add_interceptor(client, interceptor)

    return option


def with_logger(logger: Logger, **settings: Unpack[LoggerOptions]) -> ClientOption:
    """Логировать запросы и ответы клиента.

    :param logger: логгер, в который пишутся запросы и ответы
    :param sanitize_keys: имена ключей метаданных и пути glom в теле сообщения, значения которых маскируются
    :param log_level: уровень логирования успешных запросов, по умолчанию из конфигурации
    :param err_log_level: уровень логирования запросов с ошибкой, по умолчанию из конфигурации
    :param json_indent: ширина отступа при форматировании JSON, по умолчанию из конфигурации
    :param use_line_breaks: разносить ли свойства лога по строкам, по умолчанию из конфигурации
    :param payload_maxlength: максимальная длина тела сообщения в логе, по умолчанию из конфигурации
    :param use_default_sanitize_keys: маскировать ли типовые секреты в дополнение к `sanitize_keys`
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        interceptor_class = AsyncLoggingInterceptor if isinstance(client, AsyncGRPCClient) else LoggingInterceptor
        _add_interceptor(
            client,
            interceptor_class(
                logger=logger,
                **settings,
            ),
        )

    return option


def with_log_sink(
    sink: LogSink,
    log_level: int | None = None,
    err_log_level: int | None = None,
) -> ClientOption:
    """Логировать запросы и ответы клиента через собственный приемник записей.

    Клиент собирает `RequestRecord` и `ResponseRecord` и выбирает уровень, приемник решает,
    куда и в каком виде запись попадет. Оформление лога — маскирование, отступы, обрезка тела —
    настраивает сам приемник, поэтому здесь этих параметров нет.

    :param sink: приемник записей о вызовах
    :param log_level: уровень логирования успешных запросов, по умолчанию из конфигурации
    :param err_log_level: уровень логирования запросов с ошибкой, по умолчанию из конфигурации
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        interceptor_class = AsyncLoggingInterceptor if isinstance(client, AsyncGRPCClient) else LoggingInterceptor
        _add_interceptor(
            client,
            interceptor_class(sink=sink, log_level=log_level, err_log_level=err_log_level),
        )

    return option


def with_autogenerated_request_id(key: str | None = None) -> ClientOption:
    """Добавлять к каждому запросу сгенерированный идентификатор.

    :param key: имя ключа метаданных, по умолчанию `x-request-id`
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        interceptor_class = (
            AsyncAutogenerateRequestIdInterceptor
            if isinstance(client, AsyncGRPCClient)
            else AutogenerateRequestIdInterceptor
        )
        _add_interceptor(client, interceptor_class(key))

    return option


def with_autogenerated_traceparent(key: str | None = None) -> ClientOption:
    """Добавлять к каждому запросу сгенерированный traceparent.

    :param key: имя ключа метаданных, по умолчанию `traceparent`
    :return: опция клиента
    """

    def option(client: BaseGRPCClient[object]) -> None:
        interceptor_class = (
            AsyncAutogenerateTraceparentInterceptor
            if isinstance(client, AsyncGRPCClient)
            else AutogenerateTraceparentInterceptor
        )
        _add_interceptor(client, interceptor_class(key))

    return option


def _add_interceptor(client: BaseGRPCClient[object], interceptor: object) -> None:
    """Добавить интерцептор к клиенту.

    Асинхронный интерцептор раскладывается по типам вызовов: иначе grpc.aio применит его
    только к одному типу запросов.

    :param client: настраиваемый клиент
    :param interceptor: интерцептор grpcio
    """
    client.add_interceptor(interceptor)


def _as_sync_auth(auth: ClientAuth | AsyncClientAuth) -> ClientAuth:
    """Проверить, что реализация авторизации подходит синхронному клиенту.

    Оба протокола объявляют методы с одинаковыми именами, поэтому различить их можно
    только по тому, объявлен ли `token()` корутиной.
    """
    if _is_async_auth(auth):
        message = "Синхронному клиенту нужна синхронная реализация ClientAuth"
        raise TypeError(message)
    return cast("ClientAuth", auth)


def _as_async_auth(auth: ClientAuth | AsyncClientAuth) -> AsyncClientAuth:
    """Проверить, что реализация авторизации подходит асинхронному клиенту."""
    if not _is_async_auth(auth):
        message = "Асинхронному клиенту нужна асинхронная реализация AsyncClientAuth"
        raise TypeError(message)
    return cast("AsyncClientAuth", auth)


def _is_async_auth(auth: ClientAuth | AsyncClientAuth) -> bool:
    return inspect.iscoroutinefunction(auth.token)
