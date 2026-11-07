from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .results import LiveSSHResult
from .utils.masking import mask_request_data, mask_response_data

if TYPE_CHECKING:
    from collections.abc import Sequence
    from logging import Logger

    from .results import SSHResult
    from .types import RequestHook, ResponseHook, StructuredLogger

type MaskPattern = str | re.Pattern[str]


def _outputs(result: SSHResult | LiveSSHResult, patterns: Sequence[MaskPattern]) -> tuple[str, str]:
    if isinstance(result, LiveSSHResult):
        return mask_response_data("\n".join(result.stdout_lines), "\n".join(result.stderr_lines), patterns)
    return mask_response_data(result.stdout, result.stderr, patterns)


def create_request_logger_hook(logger: Logger, mask_patterns: Sequence[MaskPattern] | None = None) -> RequestHook:
    """Create a sanitized request log callback.

    :param logger: Standard logger.
    :param mask_patterns: Literal secrets or regular expressions.
    :return: Request observer.
    """

    def log_request(*, host: str, port: int, username: str | None, command: str) -> None:
        logger.info(
            "SSH request: host=%s, port=%s, username=%s, command=%s",
            host,
            port,
            username,
            mask_request_data(command, mask_patterns or ()),
        )

    return log_request


def create_response_logger_hook(logger: Logger, mask_patterns: Sequence[MaskPattern] | None = None) -> ResponseHook:
    """Create a sanitized command result log callback.

    :param logger: Standard logger.
    :param mask_patterns: Literal secrets or regular expressions.
    :return: Response observer.
    """

    def log_response(*, host: str, command: str, result: SSHResult | LiveSSHResult) -> None:
        output, errors = _outputs(result, mask_patterns or ())
        logger.info(
            "SSH response: host=%s, exit_code=%s, stdout=%s, stderr=%s, command=%s",
            host,
            result.exit_code,
            output,
            errors,
            mask_request_data(command, mask_patterns or ()),
        )

    return log_response


def create_request_structlogger_hook(
    logger: StructuredLogger,
    mask_patterns: Sequence[MaskPattern] | None = None,
) -> RequestHook:
    """Create a sanitized structured request observer.

    :param logger: Structured logger.
    :param mask_patterns: Literal secrets or regular expressions.
    :return: Request observer.
    """

    def log_request(*, host: str, port: int, username: str | None, command: str) -> None:
        logger.info(
            "ssh request sent",
            host=host,
            port=port,
            username=username,
            command=mask_request_data(command, mask_patterns or ()),
        )

    return log_request


def create_response_structlogger_hook(
    logger: StructuredLogger,
    mask_patterns: Sequence[MaskPattern] | None = None,
) -> ResponseHook:
    """Create a sanitized structured command result observer.

    :param logger: Structured logger.
    :param mask_patterns: Literal secrets or regular expressions.
    :return: Response observer.
    """

    def log_response(*, host: str, command: str, result: SSHResult | LiveSSHResult) -> None:
        output, errors = _outputs(result, mask_patterns or ())
        logger.info(
            "ssh response received",
            host=host,
            exit_code=result.exit_code,
            stdout=output,
            stderr=errors,
            command=mask_request_data(command, mask_patterns or ()),
        )

    return log_response
