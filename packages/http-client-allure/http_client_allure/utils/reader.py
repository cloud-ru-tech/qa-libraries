import httpx


def read_request_body(request: httpx.Request) -> bytes:
    """Прочитать тело запроса.

    httpx кеширует прочитанное тело и подставляет его обратно в поток,
    поэтому отправку это не ломает.
    """
    return request.read()


async def aread_request_body(request: httpx.Request) -> bytes:
    """Асинхронный вариант read_request_body."""
    return await request.aread()


def peek_request_body(request: httpx.Request) -> bytes | None:
    """Вернуть тело запроса, только если оно уже загружено.

    Используется на потоковых запросах: чтение несозданного тела съело бы поток выгрузки.

    :return: тело запроса либо None, если тело потоковое и еще не прочитано
    """
    if not _is_loaded(request):
        return None

    return request.read()


def read_response_body(response: httpx.Response, *, streaming: bool) -> bytes | None:
    """Прочитать тело ответа, кроме потокового.

    :param streaming: ответ получен в потоковом режиме и читать его нельзя
    :return: тело ответа либо None для потокового ответа
    """
    if streaming:
        return None

    return response.read()


async def aread_response_body(response: httpx.Response, *, streaming: bool) -> bytes | None:
    """Асинхронный вариант read_response_body."""
    if streaming:
        return None

    return await response.aread()


def peek_response_body(response: httpx.Response) -> bytes | None:
    """Вернуть тело потокового ответа, только если его уже прочитал вызывающий код.

    :return: тело ответа либо None, если поток не вычитывали
    """
    if not _is_loaded(response):
        return None

    return response.read()


def _is_loaded(message: httpx.Request | httpx.Response) -> bool:
    """Проверить, что httpx уже загрузил тело в память."""
    return hasattr(message, "_content")
