import grpc


class GRPCClientError(Exception):
    """Base library error."""


class MessageUndefinedError(GRPCClientError):
    """Error for a missing response message.

    Raised when accessing the message of a failed response.
    """

    def __init__(self, status_code: grpc.StatusCode, details: str) -> None:
        """Create an instance with the supplied settings."""
        super().__init__(
            f"Ответ на gRPC-запрос не содержит сообщения: status_code = {status_code}, details = {details}"
        )
        self.status_code = status_code
        self.details = details


class ResponseStatusError(GRPCClientError):
    """Error for an unsuccessful response status.

    Raised by `raise_for_status()` for a response whose code is not OK.
    """

    def __init__(self, status_code: grpc.StatusCode, details: str) -> None:
        """Create an instance with the supplied settings."""
        super().__init__(f"gRPC-запрос завершился с ошибкой: status_code = {status_code}, details = {details}")
        self.status_code = status_code
        self.details = details


class StreamConsumedError(GRPCClientError):
    """Error when reading a stream again.

    A gRPC stream can be read only once: received messages are not buffered.
    To access messages again, save them using `collect()`.
    """

    def __init__(self) -> None:
        """Create an instance with the supplied settings."""
        super().__init__("Поток уже прочитан, повторное чтение невозможно: сохраните сообщения через collect()")


class StreamNotConsumedError(GRPCClientError):
    """Error when accessing the final status of an unread stream.

    The server reports final status and trailing metadata only after stream completion,
    so they remain unavailable until reading finishes.
    """

    def __init__(self, attribute: str) -> None:
        """Create an instance with the supplied settings."""
        super().__init__(
            f"Значение «{attribute}» доступно только после завершения потока: дочитайте поток или вызовите collect()"
        )
