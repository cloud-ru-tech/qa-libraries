import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypedDict, Unpack, cast, override

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from grpc_client.config import LOGGING_CONFIG
from grpc_client.types import MetadataType

from .sanitizer import DEFAULT_SANITIZE_KEYS, sanitize, sanitize_metadata

TRUNCATION_SUFFIX = "... <обрезано>"


class FormatOptions(TypedDict, total=False):
    """Параметры оформления записей логгера."""

    sanitize_keys: Sequence[str] | None
    json_indent: int | None
    use_line_breaks: bool | None
    payload_maxlength: int | None
    use_default_sanitize_keys: bool


class LoggerOptions(FormatOptions, total=False):
    """Оформление и уровни записей логгера."""

    log_level: int | None
    err_log_level: int | None


class BytesEncoder(json.JSONEncoder):
    """Кодировщик, превращающий байты в строки."""

    @override
    def default(self, o: object) -> object:
        if isinstance(o, bytes):
            try:
                return o.decode("utf-8")
            except UnicodeDecodeError:
                return "<двоичные данные>"
        return cast("object", super().default(o))


@dataclass(frozen=True, slots=True, kw_only=True)
class LogFormat:
    """Правила оформления логов gRPC-запросов и ответов."""

    # Ключи метаданных и пути glom в теле сообщения, значения которых маскируются.
    sanitize_keys: Sequence[str] = field(default_factory=tuple)

    # Ширина отступа при форматировании JSON.
    json_indent: int | None = None

    # Разносить ли свойства лога по строкам.
    use_line_breaks: bool = False

    # Максимальная длина тела сообщения в логе.
    payload_maxlength: int | None = None

    @property
    def separator(self) -> str:
        """Разделитель свойств лога."""
        return "\n" if self.use_line_breaks else " "

    @classmethod
    def from_config(
        cls,
        *,
        sanitize_keys: Sequence[str] | None = None,
        json_indent: int | None = None,
        use_line_breaks: bool | None = None,
        payload_maxlength: int | None = None,
        use_default_sanitize_keys: bool = True,
    ) -> "LogFormat":
        """Собрать правила оформления, подставив вместо `None` значения общей конфигурации.

        Конфигурация читается в момент вызова, поэтому `configure_logging` нужно вызывать
        до сборки клиента.

        :param sanitize_keys: имена ключей метаданных и пути glom в теле сообщения, значения которых маскируются
        :param json_indent: ширина отступа при форматировании JSON, по умолчанию из конфигурации
        :param use_line_breaks: разносить ли свойства лога по строкам, по умолчанию из конфигурации
        :param payload_maxlength: максимальная длина тела сообщения в логе, по умолчанию из конфигурации
        :param use_default_sanitize_keys: маскировать ли типовые секреты в дополнение к `sanitize_keys`
        :return: правила оформления логов
        """
        keys = list(sanitize_keys or [])
        if use_default_sanitize_keys:
            keys.extend(key for key in DEFAULT_SANITIZE_KEYS if key not in keys)

        return cls(
            sanitize_keys=tuple(keys),
            json_indent=json_indent if json_indent is not None else LOGGING_CONFIG.json_indent,
            use_line_breaks=use_line_breaks if use_line_breaks is not None else LOGGING_CONFIG.use_line_breaks,
            payload_maxlength=(
                payload_maxlength if payload_maxlength is not None else LOGGING_CONFIG.payload_log_maxlength
            ),
        )


def request_log(
    trace_id: str,
    method: str,
    message: Message | None,
    metadata: MetadataType | None,
    log_format: LogFormat,
) -> str:
    """Собрать лог отправленного gRPC-запроса.

    :param trace_id: идентификатор, связывающий запрос с ответом
    :param method: полное имя вызываемого метода
    :param message: отправляемое сообщение, отсутствует для клиентских потоков
    :param metadata: метаданные запроса
    :param log_format: правила оформления лога
    :return: строка лога
    """
    parts = [f"GRPC request sent: id={trace_id}", f"Method: {method}"]
    parts.append(f"Payload: {_payload(message, log_format)}" if message is not None else "Payload: <поток сообщений>")
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


class ResponseLogFields(TypedDict):
    """Данные записи лога."""

    trace_id: str
    method: str
    status_code: grpc.StatusCode
    message: Message | None
    metadata: MetadataType | None
    log_format: LogFormat


def response_log(**fields: Unpack[ResponseLogFields]) -> str:
    """Собрать лог полученного gRPC-ответа.

    :param trace_id: идентификатор, связывающий запрос с ответом
    :param method: полное имя вызванного метода
    :param status_code: код статуса ответа
    :param message: ответное сообщение, отсутствует для серверных потоков
    :param metadata: метаданные ответа
    :param log_format: правила оформления лога
    :return: строка лога
    """
    trace_id = fields["trace_id"]
    method = fields["method"]
    status_code = fields["status_code"]
    message = fields["message"]
    metadata = fields["metadata"]
    log_format = fields["log_format"]
    parts = [
        f"GRPC response received: id={trace_id}",
        f"Status: {_status(status_code)}",
        f"Method: {method}",
    ]
    if message is not None:
        parts.append(f"Payload: {_payload(message, log_format)}")
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


class StreamResponseLogFields(TypedDict):
    """Данные записи лога."""

    trace_id: str
    method: str
    status_code: grpc.StatusCode
    messages_count: int
    metadata: MetadataType | None
    log_format: LogFormat


def stream_response_log(**fields: Unpack[StreamResponseLogFields]) -> str:
    """Собрать лог завершившегося потока ответных сообщений.

    Сами сообщения в лог не попадают: поток может быть сколь угодно длинным, а его вычитывание
    ради лога изменило бы поведение вызова.

    :param trace_id: идентификатор, связывающий запрос с ответом
    :param method: полное имя вызванного метода
    :param status_code: итоговый код статуса потока
    :param messages_count: количество полученных сообщений
    :param metadata: метаданные ответа
    :param log_format: правила оформления лога
    :return: строка лога
    """
    trace_id = fields["trace_id"]
    method = fields["method"]
    status_code = fields["status_code"]
    messages_count = fields["messages_count"]
    metadata = fields["metadata"]
    log_format = fields["log_format"]
    parts = [
        f"GRPC stream finished: id={trace_id}",
        f"Status: {_status(status_code)}",
        f"Method: {method}",
        f"Messages: {messages_count}",
    ]
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


class ErrorLogFields(TypedDict):
    """Данные записи лога."""

    trace_id: str
    method: str
    status_code: grpc.StatusCode
    details: str
    metadata: MetadataType | None
    log_format: LogFormat


def error_log(**fields: Unpack[ErrorLogFields]) -> str:
    """Собрать лог gRPC-запроса, завершившегося ошибкой.

    :param trace_id: идентификатор, связывающий запрос с ответом
    :param method: полное имя вызванного метода
    :param status_code: код статуса ответа
    :param details: текст ошибки от сервиса
    :param metadata: метаданные ответа
    :param log_format: правила оформления лога
    :return: строка лога
    """
    trace_id = fields["trace_id"]
    method = fields["method"]
    status_code = fields["status_code"]
    details = fields["details"]
    metadata = fields["metadata"]
    log_format = fields["log_format"]
    parts = [
        f"GRPC error occurred: id={trace_id}",
        f"Status: {_status(status_code)}",
        f"Method: {method}",
        f"Error: {details}",
    ]
    parts.extend(_metadata_parts(metadata, log_format))
    return log_format.separator.join(parts)


def _status(status_code: grpc.StatusCode) -> str:
    """Собрать текстовое представление кода статуса."""
    code, _ = cast("tuple[int, str]", status_code.value)
    return f"{code} ({status_code.name})"


def _metadata_parts(metadata: MetadataType | None, log_format: LogFormat) -> list[str]:
    """Собрать часть лога с метаданными.

    Значения повторяющегося ключа собираются в список: обычный словарь оставил бы
    только последнее из них, и лог перестал бы соответствовать отправленным метаданным.
    """
    items = sanitize_metadata(metadata, log_format.sanitize_keys)
    if not items:
        return []

    grouped: dict[str, object] = {}
    for name, value in items:
        if name not in grouped:
            grouped[name] = value
        elif isinstance(previous := grouped[name], list):
            cast("list[object]", previous).append(value)
        else:
            grouped[name] = [grouped[name], value]

    return [f"Metadata: {_to_json(grouped, log_format.json_indent)}"]


PAYLOAD_UNAVAILABLE = "<не удалось подготовить тело сообщения>"


def _payload(message: Message, log_format: LogFormat) -> str:
    """Собрать часть лога с телом сообщения.

    Ошибка подготовки лога не должна мешать запросу: лог собирается до отправки, и падение
    здесь — например, на предельно вложенном сообщении — сорвало бы сам вызов.
    """
    try:
        payload = cast("dict[str, object]", MessageToDict(message, always_print_fields_with_no_presence=True))
        masked = sanitize(payload, log_format.sanitize_keys)
        return _truncate(_to_json(masked, log_format.json_indent), log_format.payload_maxlength)
    except RecursionError:
        return PAYLOAD_UNAVAILABLE
    except Exception:  # noqa: BLE001 — сюда попадают и ошибки glom-путей, и сбои сериализации
        return PAYLOAD_UNAVAILABLE


def _to_json(value: dict[str, object], indent: int | None) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=False, cls=cast("type[json.JSONEncoder]", BytesEncoder))


def _truncate(value: str, maxlength: int | None) -> str:
    if maxlength is None or len(value) <= maxlength:
        return value
    return value[:maxlength] + TRUNCATION_SUFFIX
