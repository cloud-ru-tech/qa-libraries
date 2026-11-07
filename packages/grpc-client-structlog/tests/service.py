from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent import futures
from typing import Protocol, cast

import grpc
from google.protobuf.struct_pb2 import Struct

SERVICE_NAME = "structlog.test.Echo"

UNARY_METHOD = f"/{SERVICE_NAME}/Unary"
SERVER_STREAM_METHOD = f"/{SERVICE_NAME}/ServerStream"
CLIENT_STREAM_METHOD = f"/{SERVICE_NAME}/ClientStream"
BIDIRECTIONAL_METHOD = f"/{SERVICE_NAME}/BidirectionalStream"

# Поля, которыми запрос просит сервис ответить ошибкой.
ERROR_CODE_FIELD = "error_code"
ERROR_REASON_FIELD = "error_reason"

# Поле, которым запрос задает длину потока ответных сообщений.
STREAM_LENGTH_FIELD = "stream_length"

# Поле, которым запрос просит сервис вернуть метаданные ответа, и ключ, под которым они вернутся.
TRAILING_METADATA_FIELD = "trailing_value"
TRAILING_METADATA_KEY = "x-trailing"

DEFAULT_STREAM_LENGTH = 3

# Порт, который сервис слушает внутри контейнера.
CONTAINER_PORT = 50051


type StructValue = bool | float | int | str | Struct | Sequence[StructValue] | Mapping[str, StructValue] | None


class _HandlerFactory(Protocol):
    def __call__(
        self,
        behavior: object,
        *,
        request_deserializer: Callable[[bytes], Struct],
        response_serializer: Callable[[Struct], bytes],
    ) -> grpc.RpcMethodHandler[Struct, Struct]: ...


def start_service(addr: str) -> grpc.Server:
    """Поднять тестовый gRPC сервис.

    Сервис отвечает на все четыре типа вызовов и по просьбе клиента завершает вызов ошибкой,
    возвращает метаданные ответа и поток заданной длины.

    :param addr: адрес, который слушать, вида `host:port`
    :returns: запущенный сервер
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers((_build_handlers(),))
    server.add_insecure_port(addr)
    server.start()
    return server


def build_message(**fields: StructValue) -> Struct:
    """Собрать сообщение тестового сервиса.

    :param fields: поля сообщения
    :returns: сообщение с указанными полями
    """
    message = Struct()
    message.update(fields)
    return message


def build_failing_message(status_code: grpc.StatusCode, reason: str) -> Struct:
    """Собрать сообщение, на которое сервис ответит ошибкой.

    :param status_code: код статуса, которым сервис завершит вызов
    :param reason: текст ошибки
    :returns: сообщение с просьбой ответить ошибкой
    """
    return build_message(**{ERROR_CODE_FIELD: status_code.name, ERROR_REASON_FIELD: reason})


def build_message_with_trailing_metadata(value: str) -> Struct:
    """Собрать сообщение, на которое сервис ответит метаданными.

    :param value: значение, которое сервис вернет ключом `TRAILING_METADATA_KEY`
    :returns: сообщение с просьбой вернуть метаданные ответа
    """
    return build_message(**{TRAILING_METADATA_FIELD: value})


def _build_handlers() -> grpc.GenericRpcHandler[Struct, Struct]:
    handlers: dict[str, grpc.RpcMethodHandler[Struct, Struct]] = {
        "Unary": cast("_HandlerFactory", grpc.unary_unary_rpc_method_handler)(
            _echo,
            request_deserializer=Struct.FromString,
            response_serializer=Struct.SerializeToString,
        ),
        "ServerStream": cast("_HandlerFactory", grpc.unary_stream_rpc_method_handler)(
            _stream_back,
            request_deserializer=Struct.FromString,
            response_serializer=Struct.SerializeToString,
        ),
        "ClientStream": cast("_HandlerFactory", grpc.stream_unary_rpc_method_handler)(
            _count_received,
            request_deserializer=Struct.FromString,
            response_serializer=Struct.SerializeToString,
        ),
        "BidirectionalStream": cast("_HandlerFactory", grpc.stream_stream_rpc_method_handler)(
            _echo_each,
            request_deserializer=Struct.FromString,
            response_serializer=Struct.SerializeToString,
        ),
    }
    return cast("grpc.GenericRpcHandler[Struct, Struct]", grpc.method_handlers_generic_handler(SERVICE_NAME, handlers))


def _echo(request: Struct, context: grpc.ServicerContext) -> Struct:
    _abort_if_asked(request, context)
    _send_trailing_metadata_if_asked(request, context)
    return request


def _stream_back(request: Struct, context: grpc.ServicerContext) -> Iterator[Struct]:
    _abort_if_asked(request, context)
    for index in range(_stream_length(request)):
        yield build_message(index=index)


def _count_received(
    request_iterator: Iterator[Struct],
    context: grpc.ServicerContext,  # noqa: ARG001 — сигнатуру обработчика задает grpcio
) -> Struct:
    return build_message(received=sum(1 for _ in request_iterator))


def _echo_each(
    request_iterator: Iterator[Struct],
    context: grpc.ServicerContext,  # noqa: ARG001 — сигнатуру обработчика задает grpcio
) -> Iterator[Struct]:
    yield from request_iterator


def _abort_if_asked(request: Struct, context: grpc.ServicerContext) -> None:
    payload = dict(request.items())
    if ERROR_CODE_FIELD not in payload:
        return

    context.abort(grpc.StatusCode[str(payload[ERROR_CODE_FIELD])], str(payload.get(ERROR_REASON_FIELD, "")))


def _send_trailing_metadata_if_asked(request: Struct, context: grpc.ServicerContext) -> None:
    value = dict(request.items()).get(TRAILING_METADATA_FIELD)
    if value is None:
        return

    context.set_trailing_metadata(((TRAILING_METADATA_KEY, str(value)),))


def _stream_length(request: Struct) -> int:
    length = dict(request.items()).get(STREAM_LENGTH_FIELD)
    return int(length) if isinstance(length, float | int) else DEFAULT_STREAM_LENGTH


if __name__ == "__main__":
    start_service(f"[::]:{CONTAINER_PORT}").wait_for_termination()
