import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final, Self, TextIO, cast

from .naming import slugify

DEFAULT_FILE_MODE: Final = 0o600
DEFAULT_DIR_MODE: Final = 0o700

# O_NOFOLLOW is POSIX-only. It prevents replacing a log file with a symlink
# in a predictable directory.
_O_NOFOLLOW: Final = cast("int", getattr(os, "O_NOFOLLOW", 0))


@dataclass(frozen=True, slots=True)
class HandlerOptions:
    """Log encoding, permissions, and filename settings."""

    name_suffix: str = ""
    encoding: str = "utf-8"
    errors: str = "backslashreplace"
    file_mode: int = DEFAULT_FILE_MODE
    dir_mode: int = DEFAULT_DIR_MODE


_DEFAULT_OPTIONS = HandlerOptions()


class LoggingContextHandler(logging.Handler):
    """Write current test logs to a separate file.

    Until a test is bound (`bind`), records go to the shared fixture file, which receives
    all logs between tests and in session-scoped fixtures.

    File switching uses the same lock as `emit`, so
    background thread logging cannot write to a closed file.
    """

    def __init__(
        self,
        output_dir: Path,
        fixtures_filename: str = "fixtures.log",
        *,
        options: HandlerOptions = _DEFAULT_OPTIONS,
    ) -> None:
        """Initialize the object.

        :param output_dir: ``output_dir`` setting value.
        :param fixtures_filename: shared fixture log filename.
        :param options: encoding, permissions, and filename suffix.
        """
        super().__init__()
        self._output_dir = output_dir
        self._name_suffix = slugify(options.name_suffix) if options.name_suffix else ""
        self._encoding = options.encoding
        self._errors = options.errors
        self._file_mode = options.file_mode

        self._fixtures_path = output_dir / fixtures_filename
        self._fixtures_stream: TextIO | None = None
        self._test_stream: TextIO | None = None
        self._test_path: Path | None = None
        self._used_names: dict[str, int] = {}
        self._closed = False

        self._create_output_dir(options.dir_mode)

    @property
    def output_dir(self) -> Path:
        """Directory where log files are written."""
        return self._output_dir

    @property
    def fixtures_file(self) -> Path:
        """File used for logs outside tests."""
        return self._fixtures_path

    @property
    def current_file(self) -> Path | None:
        """Current test log file, or None if no test is bound."""
        return self._test_path

    def bind(self, test_name: str) -> Path:
        """Route logs to a separate test file.

        :param test_name: readable test name used as the filename base
        :return: path to the created log file
        :raises RuntimeError: if the previous test was not unbound
        """
        with self._locked():
            if self._closed:
                message = "cannot bind a closed LoggingContextHandler"
                raise RuntimeError(message)
            if self._test_stream is not None:
                message = (
                    f"logging context is already bound to «{self._test_path}»; "
                    f"call unbind() before binding «{test_name}»"
                )
                raise RuntimeError(message)

            path = self._reserve_path(test_name)
            self._test_stream = self._open(path, append=False)
            self._test_path = path
            return path

    def unbind(self) -> None:
        """Route logs back to the shared fixture file."""
        with self._locked():
            self._close_stream(self._test_stream)
            self._test_stream = None
            self._test_path = None

    def emit(self, record: logging.LogRecord) -> None:
        """Write a message to the current test file or the fixture file."""
        if self._closed:
            return

        try:
            stream = self._test_stream or self._fixtures()
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:  # noqa: BLE001 - logging.Handler contract
            self.handleError(record)

    def flush(self) -> None:
        """Flush buffers of already open files.

        Never open files: `logging.shutdown()` calls flush on all
        handlers, and creating a file at this stage would be a side effect.
        """
        with self._locked():
            for stream in (self._test_stream, self._fixtures_stream):
                if stream is not None and not stream.closed:
                    stream.flush()

    def close(self) -> None:
        """Close all open files. Idempotent."""
        with self._locked():
            if self._closed:
                return
            self._closed = True
            self._close_stream(self._test_stream)
            self._close_stream(self._fixtures_stream)
            self._test_stream = None
            self._test_path = None
            self._fixtures_stream = None
        super().close()

    def __enter__(self) -> Self:
        """Get a handler that closes automatically.

        :return: current handler.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close files on context exit."""
        self.close()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Acquire the handler lock also used by `logging` when calling `emit`."""
        self.acquire()
        try:
            yield
        finally:
            self.release()

    def _create_output_dir(self, dir_mode: int) -> None:
        if self._output_dir.exists():
            return

        self._output_dir.mkdir(parents=True, exist_ok=True)
        # Some filesystems do not support setting permissions; preserving logs matters more.
        with suppress(OSError):
            self._output_dir.chmod(dir_mode)

    def _fixtures(self) -> TextIO:
        """Open the fixture file once and keep it open until `close()`.

        Reopening would truncate logs already written.
        """
        if self._fixtures_stream is None:
            self._fixtures_stream = self._open(self._fixtures_path, append=False)
        return self._fixtures_stream

    def _reserve_path(self, test_name: str) -> Path:
        """Choose an available filename, adding a numeric suffix on collision."""
        slug = slugify(test_name)
        if self._name_suffix:
            # Different processes use different files even when test names match.
            slug = f"{slug}.{self._name_suffix}"

        attempt = self._used_names.get(slug, 0) + 1
        self._used_names[slug] = attempt

        filename = f"{slug}.log" if attempt == 1 else f"{slug}.{attempt}.log"
        path = self._output_dir / filename

        # slugify excludes path separators, so escaping output_dir is impossible.
        # This check guards against a slugify regression.
        if path.parent != self._output_dir:
            message = f"refusing to write log outside of {self._output_dir}: {path}"
            raise RuntimeError(message)

        return path

    def _open(self, path: Path, *, append: bool) -> TextIO:
        flags = os.O_WRONLY | os.O_CREAT | _O_NOFOLLOW
        flags |= os.O_APPEND if append else os.O_TRUNC
        descriptor = os.open(path, flags, self._file_mode)
        return os.fdopen(
            descriptor,
            "a" if append else "w",
            encoding=self._encoding,
            errors=self._errors,
        )

    @staticmethod
    def _close_stream(stream: TextIO | None) -> None:
        if stream is None or stream.closed:
            return
        try:
            stream.flush()
        finally:
            stream.close()
