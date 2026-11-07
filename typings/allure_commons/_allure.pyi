from collections.abc import Callable, Mapping
from os import PathLike
from types import TracebackType
from typing import Protocol, overload, type_check_only

from .types import AttachmentType

@type_check_only
class LabelDecorator(Protocol):
    def __call__[T](self, target: T) -> T: ...

def title(test_title: str) -> LabelDecorator: ...
def feature(*features: str) -> LabelDecorator: ...

class StepContext:
    def __init__(self, title: str, params: Mapping[str, object]) -> None: ...
    def __enter__(self) -> None: ...
    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None: ...
    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, R]: ...

@overload
def step(title: str) -> StepContext: ...
@overload
def step[**P, R](title: Callable[P, R]) -> Callable[P, R]: ...

class Attach:
    def __call__(
        self,
        body: str | bytes,
        name: str | None = ...,
        attachment_type: AttachmentType | str | None = ...,
        extension: str | None = ...,
    ) -> None: ...
    def file(
        self,
        source: str | PathLike[str],
        name: str | None = ...,
        attachment_type: AttachmentType | str | None = ...,
        extension: str | None = ...,
    ) -> None: ...

attach: Attach
