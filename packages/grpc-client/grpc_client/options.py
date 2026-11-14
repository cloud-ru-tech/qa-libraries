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
    """Set the default call timeout.

    :param timeout: time in seconds; `None` means unlimited
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.timeout = timeout

    return option


def with_insecure_channel() -> ClientOption:
    """Use an unencrypted channel.

    Transmitted data, including authorization tokens, is unprotected. Use only
    for local debugging and test environments.

    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.secure = False

    return option


def with_ssl_credentials(credentials: grpc.ChannelCredentials) -> ClientOption:
    """Set TLS credentials for the channel.

    :param credentials: channel credentials, for example with a corporate root certificate
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.secure = True
        client.ssl_credentials = credentials

    return option


def with_root_certificates(root_certificates: bytes) -> ClientOption:
    """Use the supplied root certificate to verify the server.

    :param root_certificates: contents of the root certificate PEM file
    :return: client option
    """
    return with_ssl_credentials(grpc.ssl_channel_credentials(root_certificates=root_certificates))


def with_channel_options(options: ChannelOptions) -> ClientOption:
    """Set low-level grpcio channel options.

    Built-in retries are also configured here through `grpc.service_config`.

    :param options: setting name and value pairs
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.channel_options = tuple(options)

    return option


def with_compression(compression: grpc.Compression) -> ClientOption:
    """Set the message compression algorithm.

    :param compression: compression algorithm
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.compression = compression

    return option


def with_default_metadata(metadata: MetadataType) -> ClientOption:
    """Add metadata to every client request.

    :param metadata: metadata added to every request
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        client.default_metadata = merge_metadata(client.default_metadata, metadata)

    return option


def with_interceptor(*interceptors: object) -> ClientOption:
    """Add interceptors to the client.

    Order matters: interceptors run in insertion order, so the logging
    interceptor should follow authentication so logs contain the final request.

    :param interceptors: synchronous or asynchronous grpcio interceptors
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        for interceptor in interceptors:
            _add_interceptor(client, interceptor)

    return option


def with_auth(auth: ClientAuth | AsyncClientAuth, *, retry_on_unauthenticated: bool = True) -> ClientOption:
    """Add an access token to every client request.

    :param auth: access token provider
    :param retry_on_unauthenticated: whether to retry a unary request with a new token after UNAUTHENTICATED
    :return: client option
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
    """Log client requests and responses.

    :param logger: logger used for requests and responses
    :param sanitize_keys: metadata key names and message body glom paths whose values are masked
    :param log_level: successful request logging level, defaults to configuration
    :param err_log_level: failed request logging level, defaults to configuration
    :param json_indent: JSON indentation width, defaults to configuration
    :param use_line_breaks: whether to put log properties on separate lines, defaults to configuration
    :param payload_maxlength: maximum logged message body length, defaults to configuration
    :param use_default_sanitize_keys: whether to mask common secrets in addition to `sanitize_keys`
    :return: client option
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
    """Log client requests and responses using a custom record sink.

    The client builds `RequestRecord` and `ResponseRecord` and selects levels; the sink decides
    where and how records are written. Log formatting, including masking, indentation, and body truncation,
    is configured by the sink itself, so these parameters are absent here.

    :param sink: call record sink
    :param log_level: successful request logging level, defaults to configuration
    :param err_log_level: failed request logging level, defaults to configuration
    :return: client option
    """

    def option(client: BaseGRPCClient[object]) -> None:
        interceptor_class = AsyncLoggingInterceptor if isinstance(client, AsyncGRPCClient) else LoggingInterceptor
        _add_interceptor(
            client,
            interceptor_class(sink=sink, log_level=log_level, err_log_level=err_log_level),
        )

    return option


def with_autogenerated_request_id(key: str | None = None) -> ClientOption:
    """Add a generated identifier to every request.

    :param key: metadata key name, defaults to `x-request-id`
    :return: client option
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
    """Add a generated traceparent to every request.

    :param key: metadata key name, defaults to `traceparent`
    :return: client option
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
    """Add an interceptor to the client.

    Split asynchronous interceptors by call type; otherwise grpc.aio applies them
    to only one request type.

    :param client: client to configure
    :param interceptor: grpcio interceptor
    """
    client.add_interceptor(interceptor)


def _as_sync_auth(auth: ClientAuth | AsyncClientAuth) -> ClientAuth:
    """Check whether the authentication implementation fits the synchronous client.

    Both protocols declare methods with the same names, so they can be distinguished
    only by whether `token()` is declared as a coroutine.
    """
    if _is_async_auth(auth):
        message = "Синхронному клиенту нужна синхронная реализация ClientAuth"
        raise TypeError(message)
    return cast("ClientAuth", auth)


def _as_async_auth(auth: ClientAuth | AsyncClientAuth) -> AsyncClientAuth:
    """Check whether the authentication implementation fits the asynchronous client."""
    if not _is_async_auth(auth):
        message = "Асинхронному клиенту нужна асинхронная реализация AsyncClientAuth"
        raise TypeError(message)
    return cast("AsyncClientAuth", auth)


def _is_async_auth(auth: ClientAuth | AsyncClientAuth) -> bool:
    return inspect.iscoroutinefunction(auth.token)
