"""Check whether a request body can be resent on retry.

A retry reuses the same `Request`. An in-memory body can be read repeatedly,
while a one-shot stream is exhausted after the first attempt:

- a generator raises `httpx.StreamConsumed` on the second attempt;
- a file object silently sends an empty body and the server returns 200: silent data loss.

Therefore rewind the body before a retry or disable retries entirely.
Recognize only stream types explicitly known to the library; treat everything else
as non-replayable: skipping a retry is preferable to sending truncated data.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, TypeGuard, cast

from httpx import Request, RequestNotRead

from ._types import is_http_request

try:  # Private httpx classes are needed to distinguish one-shot streams from replayable streams
    from httpx._content import AsyncIteratorByteStream, IteratorByteStream
    from httpx._multipart import MultipartStream

    ITERATOR_STREAMS: tuple[type[object], ...] = (IteratorByteStream, AsyncIteratorByteStream)
    MULTIPART_STREAMS: tuple[type[object], ...] = (MultipartStream,)
except ImportError:  # pragma: no cover - httpx internals have changed
    ITERATOR_STREAMS = ()
    MULTIPART_STREAMS = ()


class _Seekable(Protocol):
    def tell(self) -> int: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...


class _Multipart(Protocol):
    fields: Sequence[object]


Rewinder = Callable[[], None]


def no_rewind() -> None:
    """Leave the body unchanged because it can be resent without preparation."""


def body_rewinder(args: Sequence[object], kwargs: Mapping[str, object] | None = None) -> Rewinder | None:
    """Prepare the request body for resending.

    Return a function to call before each attempt, or `None`
    if the body cannot be resent and retries are forbidden.
    """
    request = _find_request(args, kwargs or {})
    if request is None or _is_buffered(request):
        return no_rewind

    stream = request.stream

    if isinstance(stream, MULTIPART_STREAMS):
        return _multipart_rewinder(cast("_Multipart", stream))

    if isinstance(stream, ITERATOR_STREAMS):
        return _rewinder_for(cast("object", getattr(stream, "_stream", None)))

    return None


def _find_request(args: Sequence[object], kwargs: Mapping[str, object]) -> Request | None:
    """Find the request in call arguments regardless of the parameter name."""
    return next((arg for arg in (*args, *kwargs.values()) if is_http_request(arg)), None)


def _rewinder_for(source: object) -> Rewinder | None:
    # A sequence (bytes, str, list, tuple) can be reread without preparation.
    if isinstance(source, Sequence):
        return no_rewind

    if not _is_seekable(source):
        return None

    start = source.tell()

    def rewind() -> None:
        source.seek(start)

    return rewind


def _multipart_rewinder(stream: _Multipart) -> Rewinder | None:
    """Let httpx reread multipart bodies, provided every part is replayable.

    A non-seekable file produces a retry body with only part headers and no file contents.
    """
    files = [file for field in stream.fields if (file := cast("object", getattr(field, "file", None))) is not None]
    replayable = (isinstance(file, Sequence) or _is_seekable(file) for file in files)

    return no_rewind if all(replayable) else None


def _is_buffered(request: Request) -> bool:
    try:
        _ = request.content
    except RequestNotRead:
        return False

    return True


def _is_seekable(source: object) -> TypeGuard[_Seekable]:
    if not callable(cast("object", getattr(source, "seek", None))) or not callable(
        cast("object", getattr(source, "tell", None))
    ):
        return False

    seekable = cast("Callable[[], bool] | None", getattr(source, "seekable", None))

    return bool(seekable()) if callable(seekable) else True
