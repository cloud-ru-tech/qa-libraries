from __future__ import annotations

from typing import TYPE_CHECKING

from .event_hooks import (
    create_request_logger_hook,
    create_request_structlogger_hook,
    create_response_logger_hook,
    create_response_structlogger_hook,
)
from .utils.retries import RetryPolicy

if TYPE_CHECKING:
    from collections.abc import Sequence
    from logging import Logger

    from .client import ClientOption, InitSSHClient
    from .event_hooks import MaskPattern
    from .types import OperationDecorator, OutputCallback, StructuredLogger


def with_request_timeout(timeout: float) -> ClientOption:
    """Set the command timeout.

    :param timeout: Maximum command duration in seconds.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.timeout = timeout

    return option


def with_connection_timeout(timeout: float) -> ClientOption:
    """Set the connection timeout.

    :param timeout: Maximum connection duration in seconds.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.connection_timeout = timeout

    return option


def with_password(username: str, password: str) -> ClientOption:
    """Select password authentication.

    :param username: SSH login name.
    :param password: Login password.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.username = username
        client.password = password
        client.private_key_path = None

    return option


def with_private_key(username: str, private_key_path: str) -> ClientOption:
    """Select private-key authentication.

    :param username: SSH login name.
    :param private_key_path: Path to the private key file.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.username = username
        client.private_key_path = private_key_path
        client.password = None

    return option


def with_known_hosts(path: str) -> ClientOption:
    """Trust server keys from an explicit OpenSSH known_hosts file.

    :param path: Path to the trusted server keys.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.known_hosts = path

    return option


def with_logger(logger: Logger, mask_patterns: Sequence[MaskPattern] | None = None) -> ClientOption:
    """Log sanitized SSH requests and command results.

    :param logger: Standard logger.
    :param mask_patterns: Literal secrets or regular expressions to mask.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.add_request_hook(create_request_logger_hook(logger, mask_patterns))
        client.add_response_hook(create_response_logger_hook(logger, mask_patterns))

    return option


def with_structlogger(logger: StructuredLogger, mask_patterns: Sequence[MaskPattern] | None = None) -> ClientOption:
    """Log sanitized structured SSH requests and command results.

    :param logger: Structured logger.
    :param mask_patterns: Literal secrets or regular expressions to mask.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.add_request_hook(create_request_structlogger_hook(logger, mask_patterns))
        client.add_response_hook(create_response_structlogger_hook(logger, mask_patterns))

    return option


def retry_if_connection_fails(
    retries_attempts_number: int,
    retries_interval_in_seconds: float,
    *,
    reraise_exception: bool = False,
) -> ClientOption:
    """Retry failed connections with a bounded delay.

    :param retries_attempts_number: Maximum attempts.
    :param retries_interval_in_seconds: Delay between attempts.
    :param reraise_exception: Propagate the final connection error.
    :return: Client option.
    """
    policy = RetryPolicy(retries_attempts_number, retries_interval_in_seconds, reraise=reraise_exception)

    def option(client: InitSSHClient) -> None:
        client.connection_retry = policy

    return option


def retry_if_command_fails(
    retries_attempts_number: int,
    retries_interval_in_seconds: float,
    *,
    reraise_exception: bool = False,
) -> ClientOption:
    """Retry raised command errors and nonzero exit codes.

    :param retries_attempts_number: Maximum attempts.
    :param retries_interval_in_seconds: Delay between attempts.
    :param reraise_exception: Propagate the final command failure.
    :return: Client option.
    """
    policy = RetryPolicy(retries_attempts_number, retries_interval_in_seconds, reraise=reraise_exception)

    def option(client: InitSSHClient) -> None:
        client.command_retry = policy

    return option


def with_connect_decorators(*decorators: OperationDecorator) -> ClientOption:
    """Register custom connection wrappers in application order.

    :param decorators: Wrappers preserving the operation's result type.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        for decorator in decorators:
            client.add_connect_decorator(decorator)

    return option


def with_execute_decorators(*decorators: OperationDecorator) -> ClientOption:
    """Register custom command wrappers in application order.

    :param decorators: Wrappers preserving the operation's result type.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        for decorator in decorators:
            client.add_execute_decorator(decorator)

    return option


def with_live_execute_callback(
    stdout_callback: OutputCallback | None = None,
    stderr_callback: OutputCallback | None = None,
) -> ClientOption:
    """Register default streaming output callbacks.

    :param stdout_callback: Observer of stdout lines.
    :param stderr_callback: Observer of stderr lines for asynchronous clients.
    :return: Client option.
    """

    def option(client: InitSSHClient) -> None:
        client.live_stdout_callback = stdout_callback
        client.live_stderr_callback = stderr_callback

    return option
