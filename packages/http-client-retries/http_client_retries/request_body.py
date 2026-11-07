"""Проверка того, можно ли переотправить тело запроса при повторе.

Повтор переиспользует тот же объект `Request`. Тело в памяти читается сколько угодно раз,
а одноразовый поток после первой попытки вычерпан:

- генератор на второй попытке отдаёт `httpx.StreamConsumed`;
- файловый объект молча отправляет пустое тело, и сервер отвечает 200 — тихая потеря данных.

Поэтому перед повтором тело либо перематывается, либо повторы запрещаются вовсе.
Распознаются только те виды потоков, которые библиотека знает поимённо; всё остальное
считается непроигрываемым — лучше отказаться от повтора, чем отправить обрезанные данные.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, TypeGuard, cast

from httpx import Request, RequestNotRead

from ._types import is_http_request

try:  # приватные классы httpx: иначе одноразовый поток не отличить от воспроизводимого
    from httpx._content import AsyncIteratorByteStream, IteratorByteStream
    from httpx._multipart import MultipartStream

    ITERATOR_STREAMS: tuple[type[object], ...] = (IteratorByteStream, AsyncIteratorByteStream)
    MULTIPART_STREAMS: tuple[type[object], ...] = (MultipartStream,)
except ImportError:  # pragma: no cover - httpx переставил внутренности
    ITERATOR_STREAMS = ()
    MULTIPART_STREAMS = ()


class _Seekable(Protocol):
    def tell(self) -> int: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...


class _Multipart(Protocol):
    fields: Sequence[object]


Rewinder = Callable[[], None]


def no_rewind() -> None:
    """Тело переотправляется само по себе, готовить его не нужно."""


def body_rewinder(args: Sequence[object], kwargs: Mapping[str, object] | None = None) -> Rewinder | None:
    """Подготовить тело запроса к повторным отправкам.

    Возвращает функцию, которую нужно вызвать перед каждой попыткой, либо `None`,
    если тело переотправить нельзя и повторы недопустимы.
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
    """Найти запрос среди аргументов вызова: имя параметра может быть любым."""
    return next((arg for arg in (*args, *kwargs.values()) if is_http_request(arg)), None)


def _rewinder_for(source: object) -> Rewinder | None:
    # Последовательность (bytes, str, list, tuple) перечитывается сама по себе.
    if isinstance(source, Sequence):
        return no_rewind

    if not _is_seekable(source):
        return None

    start = source.tell()

    def rewind() -> None:
        source.seek(start)

    return rewind


def _multipart_rewinder(stream: _Multipart) -> Rewinder | None:
    """Multipart httpx перечитывает сам, но только пока каждая часть воспроизводима.

    Неперематываемый файл даёт на повторе тело без его содержимого — одни заголовки частей.
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
