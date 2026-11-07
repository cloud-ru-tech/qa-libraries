from dataclasses import dataclass

import grpc

from .metadata import merge_metadata
from .types import MetadataType


class _UseClientDefault:
    """Маркер параметра вызова, значение которого берется из настроек клиента.

    Нужен, чтобы отличить «параметр не задан» от явно переданного `None`:
    `timeout=None` означает вызов без ограничения по времени.
    """

    def __repr__(self) -> str:
        """Вернуть строковое представление метаданных."""
        return "USE_CLIENT_DEFAULT"

    def __bool__(self) -> bool:
        return False


USE_CLIENT_DEFAULT = _UseClientDefault()


@dataclass(frozen=True, slots=True, kw_only=True)
class CallOptions:
    """Параметры одного gRPC вызова.

    Незаданные параметры берутся из настроек клиента.
    """

    # Ограничение времени вызова в секундах. `None` — вызов без ограничения.
    timeout: float | _UseClientDefault | None = USE_CLIENT_DEFAULT

    # Метаданные запроса, добавляемые к метаданным клиента.
    metadata: MetadataType | None = None

    # Учетные данные конкретного вызова.
    credentials: grpc.CallCredentials | None = None

    # Ждать готовности канала вместо немедленной ошибки UNAVAILABLE.
    wait_for_ready: bool | None = None

    # Алгоритм сжатия сообщений вызова.
    compression: grpc.Compression | None = None

    def merge(self, other: "CallOptions") -> "CallOptions":
        """Наложить параметры вызова поверх текущих.

        Метаданные объединяются, остальные заданные параметры `other` вытесняют текущие.

        :param other: параметры с более высоким приоритетом
        :return: объединенные параметры
        """
        return CallOptions(
            timeout=self.timeout if isinstance(other.timeout, _UseClientDefault) else other.timeout,
            metadata=merge_metadata(self.metadata, other.metadata),
            credentials=other.credentials if other.credentials is not None else self.credentials,
            wait_for_ready=other.wait_for_ready if other.wait_for_ready is not None else self.wait_for_ready,
            compression=other.compression if other.compression is not None else self.compression,
        )

    def resolve_timeout(self, default: float | None) -> float | None:
        """Вычислить итоговое ограничение времени вызова.

        :param default: значение, заданное клиентом
        :return: ограничение времени в секундах либо None, если ограничения нет
        """
        return default if isinstance(self.timeout, _UseClientDefault) else self.timeout
