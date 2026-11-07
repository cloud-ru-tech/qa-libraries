import grpc


class GRPCClientError(Exception):
    """Базовая ошибка библиотеки."""


class MessageUndefinedError(GRPCClientError):
    """Ошибка отсутствия ответного сообщения.

    Возникает при обращении к сообщению ответа, полученного с ошибкой.
    """

    def __init__(self, status_code: grpc.StatusCode, details: str) -> None:
        """Создать экземпляр с переданными настройками."""
        super().__init__(
            f"Ответ на gRPC-запрос не содержит сообщения: status_code = {status_code}, details = {details}"
        )
        self.status_code = status_code
        self.details = details


class ResponseStatusError(GRPCClientError):
    """Ошибка неуспешного статуса ответа.

    Возникает при вызове `raise_for_status()` у ответа с кодом, отличным от OK.
    """

    def __init__(self, status_code: grpc.StatusCode, details: str) -> None:
        """Создать экземпляр с переданными настройками."""
        super().__init__(f"gRPC-запрос завершился с ошибкой: status_code = {status_code}, details = {details}")
        self.status_code = status_code
        self.details = details


class StreamConsumedError(GRPCClientError):
    """Ошибка повторного чтения потока.

    Поток gRPC читается только один раз: полученные сообщения не буферизуются.
    Чтобы обратиться к сообщениям повторно, сохраните их через `collect()`.
    """

    def __init__(self) -> None:
        """Создать экземпляр с переданными настройками."""
        super().__init__("Поток уже прочитан, повторное чтение невозможно: сохраните сообщения через collect()")


class StreamNotConsumedError(GRPCClientError):
    """Ошибка обращения к итоговому статусу непрочитанного потока.

    Сервер сообщает итоговый статус и trailing-метаданные только после завершения потока,
    поэтому до окончания чтения они недоступны.
    """

    def __init__(self, attribute: str) -> None:
        """Создать экземпляр с переданными настройками."""
        super().__init__(
            f"Значение «{attribute}» доступно только после завершения потока: дочитайте поток или вызовите collect()"
        )
