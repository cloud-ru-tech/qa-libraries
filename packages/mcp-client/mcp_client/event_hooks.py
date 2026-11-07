"""Sanitized event hooks for MCP requests and responses."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from logging import Logger

    from .custom_types import RequestHook, ResponseHook, StructuredLogger
    from .results import ToolCallResponse

type MaskPattern = str | re.Pattern[str]


def _sanitize(value: object, patterns: Sequence[MaskPattern]) -> object:
    if isinstance(value, Mapping):
        return {
            key: "****" if _matches(str(key), patterns) else _sanitize(item, patterns)
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, patterns) for item in cast("Sequence[object]", value)]
    if isinstance(value, str):
        return _sanitize_text(value, patterns)
    return value


def _sanitize_text(value: str, patterns: Sequence[MaskPattern]) -> str:
    if value.startswith(("{", "[")):
        try:
            structured = cast("object", json.loads(value))
        except json.JSONDecodeError:
            pass
        else:
            return json.dumps(_sanitize(structured, patterns), ensure_ascii=False)
    masked = value
    for pattern in patterns:
        masked = masked.replace(pattern, "****") if isinstance(pattern, str) else pattern.sub("****", masked)
    return masked


def _matches(key: str, patterns: Sequence[MaskPattern]) -> bool:
    return any(key == pattern if isinstance(pattern, str) else bool(pattern.search(key)) for pattern in patterns)


def create_request_logger_hook(logger: Logger, mask_patterns: Sequence[MaskPattern] = ()) -> RequestHook:
    """Create an observer masking matching keys and text in request logs.

    :param logger: Standard logger.
    :param mask_patterns: Sensitive keys or text patterns.
    :return: Request observer.
    """

    def log_request(*, tool_name: str, arguments: Mapping[str, object], metadata: Mapping[str, object] | None) -> None:
        logger.info(
            "MCP request: tool_name=%s, arguments=%s, metadata=%s",
            tool_name,
            _sanitize(arguments, mask_patterns),
            _sanitize(metadata, mask_patterns),
        )

    return log_request


def create_response_logger_hook(logger: Logger, mask_patterns: Sequence[MaskPattern] = ()) -> ResponseHook:
    """Create a sanitized response observer.

    :param logger: Standard logger.
    :param mask_patterns: Sensitive keys or text patterns.
    :return: Response observer.
    """

    def log_response(*, tool_name: str, response: ToolCallResponse) -> None:
        logger.info(
            "MCP response: tool_name=%s, is_success=%s, content=%s",
            tool_name,
            response.is_success,
            _sanitize(cast("dict[str, object]", response.result.model_dump(mode="json")), mask_patterns),
        )

    return log_response


def create_request_structlogger_hook(
    logger: StructuredLogger,
    mask_patterns: Sequence[MaskPattern] = (),
) -> RequestHook:
    """Create a sanitized structured request observer.

    :param logger: Structured logger.
    :param mask_patterns: Sensitive keys or text patterns.
    :return: Request observer.
    """

    def log_request(*, tool_name: str, arguments: Mapping[str, object], metadata: Mapping[str, object] | None) -> None:
        logger.info(
            "mcp request sent",
            tool_name=tool_name,
            arguments=_sanitize(arguments, mask_patterns),
            metadata=_sanitize(metadata, mask_patterns),
        )

    return log_request


def create_response_structlogger_hook(
    logger: StructuredLogger,
    mask_patterns: Sequence[MaskPattern] = (),
) -> ResponseHook:
    """Create a sanitized structured response observer.

    :param logger: Structured logger.
    :param mask_patterns: Sensitive keys or text patterns.
    :return: Response observer.
    """

    def log_response(*, tool_name: str, response: ToolCallResponse) -> None:
        logger.info(
            "mcp response received",
            tool_name=tool_name,
            is_success=response.is_success,
            content=_sanitize(cast("dict[str, object]", response.result.model_dump(mode="json")), mask_patterns),
        )

    return log_response
