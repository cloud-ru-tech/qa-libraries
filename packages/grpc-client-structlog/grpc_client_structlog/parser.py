import json
import logging
from typing import cast

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from grpc_client import RequestRecord, ResponseRecord
from grpc_client.types import MetadataType
from grpc_client.utils.logutils import PAYLOAD_UNAVAILABLE, TRUNCATION_SUFFIX, BytesEncoder, LogFormat
from grpc_client.utils.sanitizer import sanitize, sanitize_metadata

_logger = logging.getLogger(__name__)

# Значение поля `body`, когда телом запроса является поток сообщений.
STREAMED_CONTENT = "<streamed content>"

# В `status_code` идет имя кода, а не его номер: по имени статус читается без справочника,
# и по нему же удобно фильтровать записи. Номер добавил бы в поле второе значение,
# а искать по строке `2 (UNKNOWN)` пришлось бы подстрокой.

# `trace_id` во всех записях дописывается последним, а не задается вместе с остальными полями:
# рендереры, сохраняющие порядок добавления (например `structlog.processors.JSONRenderer`),
# выводят поля в этом же порядке, и служебный идентификатор не должен разрывать данные вызова.


def parse_request(record: RequestRecord, log_format: LogFormat) -> dict[str, object]:
    """Собрать поля структурированного лога отправленного gRPC-запроса.

    :param record: данные запроса
    :param log_format: правила оформления лога
    :returns: поля структурированного лога запроса
    """
    properties: dict[str, object] = {
        "method": record.method,
        "body": _parse_body(record.message, log_format) if record.message is not None else STREAMED_CONTENT,
    }
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def parse_response(record: ResponseRecord, log_format: LogFormat) -> dict[str, object]:
    """Собрать поля структурированного лога полученного gRPC-ответа.

    :param record: данные завершившегося вызова
    :param log_format: правила оформления лога
    :returns: поля структурированного лога ответа
    """
    properties: dict[str, object] = {"method": record.method, "status_code": record.status_code.name}
    if record.message is not None:
        properties["body"] = _parse_body(record.message, log_format)
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def parse_stream_response(record: ResponseRecord, log_format: LogFormat) -> dict[str, object]:
    """Собрать поля структурированного лога завершившегося потока ответных сообщений.

    Сами сообщения в лог не попадают: поток может быть сколь угодно длинным, а его вычитывание
    ради лога изменило бы поведение вызова.

    :param record: данные завершившегося потока
    :param log_format: правила оформления лога
    :returns: поля структурированного лога завершившегося потока
    """
    properties: dict[str, object] = {
        "method": record.method,
        "status_code": record.status_code.name,
        "messages_count": record.messages_count,
    }
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def parse_error(record: ResponseRecord, log_format: LogFormat) -> dict[str, object]:
    """Собрать поля структурированного лога вызова, завершившегося ошибкой.

    :param record: данные завершившегося вызова
    :param log_format: правила оформления лога
    :returns: поля структурированного лога ошибки
    """
    properties: dict[str, object] = {
        "method": record.method,
        "status_code": record.status_code.name,
        "details": record.details,
    }
    if record.messages_count is not None:
        properties["messages_count"] = record.messages_count
    if (metadata_field := _parse_metadata(record.metadata, log_format)) is not None:
        properties["metadata"] = metadata_field

    properties["trace_id"] = record.trace_id
    return properties


def _parse_metadata(metadata: MetadataType | None, log_format: LogFormat) -> str | None:
    """Собрать значение поля с метаданными.

    Значения повторяющегося ключа собираются в список: обычный словарь оставил бы
    только последнее из них, и лог перестал бы соответствовать отправленным метаданным.

    :param metadata: метаданные запроса или ответа
    :param log_format: правила оформления лога
    :returns: метаданные в виде JSON либо None, если их нет
    """
    items = sanitize_metadata(metadata, log_format.sanitize_keys)
    if not items:
        return None

    grouped: dict[str, object] = {}
    for name, value in items:
        if name not in grouped:
            grouped[name] = value
        elif isinstance(previous := grouped[name], list):
            cast("list[object]", previous).append(value)
        else:
            grouped[name] = [grouped[name], value]

    return _to_json(grouped, log_format.json_indent)


def _parse_body(message: Message, log_format: LogFormat) -> str:
    """Собрать значение поля с телом сообщения.

    Ошибка подготовки лога не должна мешать запросу: лог собирается до отправки, и падение
    здесь — например, на предельно вложенном сообщении — сорвало бы сам вызов.

    :param message: сообщение запроса или ответа
    :param log_format: правила оформления лога
    :returns: тело сообщения в виде JSON либо маркер недоступного тела
    """
    try:
        payload = cast("dict[str, object]", MessageToDict(message, always_print_fields_with_no_presence=True))
        masked = sanitize(payload, log_format.sanitize_keys)
        return _truncate(_to_json(masked, log_format.json_indent), log_format.payload_maxlength)
    except Exception:
        _logger.warning("Не удалось подготовить тело сообщения gRPC", exc_info=True)
        return PAYLOAD_UNAVAILABLE


def _to_json(value: dict[str, object], indent: int | None) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=False, cls=cast("type[json.JSONEncoder]", BytesEncoder))


def _truncate(value: str, maxlength: int | None) -> str:
    if maxlength is None or len(value) <= maxlength:
        return value
    return value[:maxlength] + TRUNCATION_SUFFIX
