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

# Request fields asking the service to return an error.
ERROR_CODE_FIELD = "error_code"
ERROR_REASON_FIELD = "error_reason"

# Request field specifying the response message stream length.
STREAM_LENGTH_FIELD = "stream_length"

# Request field asking the service to return response metadata and the key used for it.
TRAILING_METADATA_FIELD = "trailing_value"
TRAILING_METADATA_KEY = "x-trailing"

DEFAULT_STREAM_LENGTH = 3

# Port the service listens on inside the container.
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
    """Start the test gRPC service.

    The service supports all four call types and can finish with an error at the client's request,
    returns response metadata and a stream of the specified length.

    :param addr: listen address such as `host:port`
    :returns: running server
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers((_build_handlers(),))
    server.add_insecure_port(addr)
    server.start()
    return server


def build_message(**fields: StructValue) -> Struct:
    """Build a test service message.

    :param fields: message fields
    :returns: message with the specified fields
    """
    message = Struct()
    message.update(fields)
    return message


def build_failing_message(status_code: grpc.StatusCode, reason: str) -> Struct:
    """Build a message that makes the service return an error.

    :param status_code: status code the service will use to finish the call
    :param reason: error text
    :returns: message requesting an error response
    """
    return build_message(**{ERROR_CODE_FIELD: status_code.name, ERROR_REASON_FIELD: reason})


def build_message_with_trailing_metadata(value: str) -> Struct:
    """Build a message that makes the service return metadata.

    :param value: value the service will return under `TRAILING_METADATA_KEY`
    :returns: message requesting response metadata
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
    context: grpc.ServicerContext,  # noqa: ARG001 - grpcio defines the handler signature
) -> Struct:
    return build_message(received=sum(1 for _ in request_iterator))


def _echo_each(
    request_iterator: Iterator[Struct],
    context: grpc.ServicerContext,  # noqa: ARG001 - grpcio defines the handler signature
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
