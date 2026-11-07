from dataclasses import dataclass
from typing import TypeVar

from google.protobuf import symbol_database
from google.protobuf.any_pb2 import Any as AnyMessage
from google.protobuf.message import Message
from google.rpc import status_pb2

from .metadata import as_metadata_items
from .types import MetadataType

# Ключ метаданных, в котором сервисы передают расширенный статус ошибки google.rpc.Status.
STATUS_DETAILS_KEY = "grpc-status-details-bin"

TDetail = TypeVar("TDetail", bound=Message)


@dataclass(frozen=True, slots=True)
class ErrorStatus:
    """Расширенный статус ошибки, переданный сервисом в google.rpc.Status.

    Помимо кода и текста ошибки сервисы кладут сюда типизированные подробности:
    какое поле не прошло валидацию, через сколько повторить запрос, какая квота исчерпана.
    """

    # Числовой код состояния из google.rpc.Code.
    code: int

    # Текст ошибки, заданный сервисом.
    message: str

    # Разобранные подробности ошибки. Неизвестные библиотеке типы остаются в виде object.
    details: tuple[Message, ...]

    def of_type(self, detail_type: type[TDetail]) -> TDetail | None:
        """Получить первую подробность ошибки указанного типа.

        :param detail_type: класс сообщения из сгенерированных pb2 модулей
        :return: подробность ошибки либо None, если подробностей такого типа нет
        """
        for detail in self.details:
            if isinstance(detail, detail_type):
                return detail
        return None

    def all_of_type(self, detail_type: type[TDetail]) -> tuple[TDetail, ...]:
        """Получить все подробности ошибки указанного типа.

        :param detail_type: класс сообщения из сгенерированных pb2 модулей
        :return: подробности ошибки в порядке получения
        """
        return tuple(detail for detail in self.details if isinstance(detail, detail_type))


def error_status_from_metadata(metadata: MetadataType | None) -> ErrorStatus | None:
    """Разобрать расширенный статус ошибки из метаданных ответа.

    :param metadata: trailing-метаданные ответа
    :return: расширенный статус либо None, если сервис его не передал или значение не разбирается
    """
    payload = _find_status_payload(metadata)
    if payload is None:
        return None

    status = status_pb2.Status()
    try:
        status.MergeFromString(payload)
    except Exception:  # noqa: BLE001 — при любом сбое разбора расширенный статус просто недоступен
        return None

    return ErrorStatus(
        code=status.code,
        message=status.message,
        details=tuple(_unpack(detail) for detail in status.details),
    )


def _find_status_payload(metadata: MetadataType | None) -> bytes | None:
    """Найти в метаданных двоичное значение расширенного статуса."""
    for key, value in as_metadata_items(metadata):
        if key.lower() == STATUS_DETAILS_KEY and isinstance(value, bytes):
            return value
    return None


def _unpack(detail: AnyMessage) -> Message:
    """Развернуть подробность ошибки в конкретное сообщение.

    Тип ищется в реестре protobuf, который наполняется импортом сгенерированных pb2 модулей.
    Если тип неизвестен, подробность остается в исходном виде.

    :param detail: подробность ошибки в виде object
    :return: разобранное сообщение либо исходный object
    """
    type_name = detail.type_url.rsplit("/", 1)[-1]

    try:
        message_class = symbol_database.Default().GetSymbol(type_name)
    except KeyError:
        return detail

    message = message_class()
    if not detail.Unpack(message):
        return detail
    return message
