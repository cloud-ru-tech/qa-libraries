from dataclasses import dataclass
from typing import TypeVar

from google.protobuf import symbol_database
from google.protobuf.any_pb2 import Any as AnyMessage
from google.protobuf.message import Message
from google.rpc import status_pb2

from .metadata import as_metadata_items
from .types import MetadataType

# Metadata key used by services to send rich google.rpc.Status errors.
STATUS_DETAILS_KEY = "grpc-status-details-bin"

TDetail = TypeVar("TDetail", bound=Message)


@dataclass(frozen=True, slots=True)
class ErrorStatus:
    """Rich error status sent by the service in google.rpc.Status.

    Besides the error code and text, services include typed details:
    which field failed validation, when to retry, and which quota was exhausted.
    """

    # Numeric status code from google.rpc.Code.
    code: int

    # Error text provided by the service.
    message: str

    # Parsed error details. Types unknown to the library remain as object.
    details: tuple[Message, ...]

    def of_type(self, detail_type: type[TDetail]) -> TDetail | None:
        """Get the first error detail of the specified type.

        :param detail_type: message class from generated pb2 modules
        :return: error detail, or None if no detail of this type is present
        """
        for detail in self.details:
            if isinstance(detail, detail_type):
                return detail
        return None

    def all_of_type(self, detail_type: type[TDetail]) -> tuple[TDetail, ...]:
        """Get all error details of the specified type.

        :param detail_type: message class from generated pb2 modules
        :return: error details in arrival order
        """
        return tuple(detail for detail in self.details if isinstance(detail, detail_type))


def error_status_from_metadata(metadata: MetadataType | None) -> ErrorStatus | None:
    """Parse the rich error status from response metadata.

    :param metadata: trailing response metadata
    :return: rich status, or None if absent or unparseable
    """
    payload = _find_status_payload(metadata)
    if payload is None:
        return None

    status = status_pb2.Status()
    try:
        status.MergeFromString(payload)
    except Exception:  # noqa: BLE001 - any parsing failure makes rich status unavailable
        return None

    return ErrorStatus(
        code=status.code,
        message=status.message,
        details=tuple(_unpack(detail) for detail in status.details),
    )


def _find_status_payload(metadata: MetadataType | None) -> bytes | None:
    """Find the binary rich status value in metadata."""
    for key, value in as_metadata_items(metadata):
        if key.lower() == STATUS_DETAILS_KEY and isinstance(value, bytes):
            return value
    return None


def _unpack(detail: AnyMessage) -> Message:
    """Unpack an error detail into a concrete message.

    Look up the type in the protobuf registry populated by importing generated pb2 modules.
    If the type is unknown, the detail remains in its original form.

    :param detail: error detail as object
    :return: parsed message or the original object
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
