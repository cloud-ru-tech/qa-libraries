import httpx


def read_request_body(request: httpx.Request) -> bytes:
    """Read the request body.

    httpx caches the body it reads and puts it back into the stream,
    so sending still works.
    """
    return request.read()


async def aread_request_body(request: httpx.Request) -> bytes:
    """Asynchronous version of read_request_body."""
    return await request.aread()


def peek_request_body(request: httpx.Request) -> bytes | None:
    """Return a request body only if it has already been loaded.

    Use for streaming requests: reading an unbuilt body would consume the upload stream.

    :return: Request body, or None if it is streaming and has not been read
    """
    if not _is_loaded(request):
        return None

    return request.read()


def read_response_body(response: httpx.Response, *, streaming: bool) -> bytes | None:
    """Read a non-streaming response body.

    :param streaming: The response is streaming and must not be read
    :return: Response body, or None for a streaming response
    """
    if streaming:
        return None

    return response.read()


async def aread_response_body(response: httpx.Response, *, streaming: bool) -> bytes | None:
    """Asynchronous version of read_response_body."""
    if streaming:
        return None

    return await response.aread()


def peek_response_body(response: httpx.Response) -> bytes | None:
    """Return a streaming response body only if the caller has already read it.

    :return: Response body, or None if the stream has not been read
    """
    if not _is_loaded(response):
        return None

    return response.read()


def _is_loaded(message: httpx.Request | httpx.Response) -> bool:
    """Check whether httpx has loaded the body into memory."""
    return hasattr(message, "_content")
