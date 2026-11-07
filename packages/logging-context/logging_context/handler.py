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

# O_NOFOLLOW есть только на POSIX. Защищает от подмены файла логов симлинком
# в предсказуемом каталоге.
_O_NOFOLLOW: Final = cast("int", getattr(os, "O_NOFOLLOW", 0))


@dataclass(frozen=True, slots=True)
class HandlerOptions:
    """Настройки кодировки, прав доступа и имён файлов логов."""

    name_suffix: str = ""
    encoding: str = "utf-8"
    errors: str = "backslashreplace"
    file_mode: int = DEFAULT_FILE_MODE
    dir_mode: int = DEFAULT_DIR_MODE


_DEFAULT_OPTIONS = HandlerOptions()


class LoggingContextHandler(logging.Handler):
    """Пишет логи текущего теста в отдельный файл.

    Пока тест не привязан (`bind`), записи идут в общий файл фикстур — туда
    попадает всё, что логируется между тестами и в session-scoped фикстурах.

    Переключение файла выполняется под тем же локом, что и `emit`, поэтому
    логирование из фоновых потоков не приводит к записи в закрытый файл.
    """

    def __init__(
        self,
        output_dir: Path,
        fixtures_filename: str = "fixtures.log",
        *,
        options: HandlerOptions = _DEFAULT_OPTIONS,
    ) -> None:
        """Инициализировать объект.

        :param output_dir: значение настройки ``output_dir``.
        :param fixtures_filename: имя общего файла логов фикстур.
        :param options: кодировка, права доступа и суффикс имени файла.
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
        """Каталог, в который пишутся файлы логов."""
        return self._output_dir

    @property
    def fixtures_file(self) -> Path:
        """Файл, в который пишутся логи вне тестов."""
        return self._fixtures_path

    @property
    def current_file(self) -> Path | None:
        """Файл логов текущего теста или None, если тест не привязан."""
        return self._test_path

    def bind(self, test_name: str) -> Path:
        """Направить логи в отдельный файл теста.

        :param test_name: читаемое имя теста, станет основой имени файла
        :return: путь до созданного файла логов
        :raises RuntimeError: если предыдущий тест не был отвязан
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
        """Вернуть логи в общий файл фикстур."""
        with self._locked():
            self._close_stream(self._test_stream)
            self._test_stream = None
            self._test_path = None

    def emit(self, record: logging.LogRecord) -> None:
        """Записать сообщение в файл текущего теста либо в файл фикстур."""
        if self._closed:
            return

        try:
            stream = self._test_stream or self._fixtures()
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:  # noqa: BLE001 — контракт logging.Handler
            self.handleError(record)

    def flush(self) -> None:
        """Сбросить буферы уже открытых файлов.

        Никогда не открывает файл: `logging.shutdown()` вызывает flush у всех
        хендлеров, и создание файла на этом этапе было бы побочным эффектом.
        """
        with self._locked():
            for stream in (self._test_stream, self._fixtures_stream):
                if stream is not None and not stream.closed:
                    stream.flush()

    def close(self) -> None:
        """Закрыть все открытые файлы. Идемпотентен."""
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
        """Получить хендлер с автоматическим закрытием.

        :return: текущий хендлер.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрыть файлы при выходе из контекста."""
        self.close()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Лок хендлера, тот же, под которым `logging` вызывает `emit`."""
        self.acquire()
        try:
            yield
        finally:
            self.release()

    def _create_output_dir(self, dir_mode: int) -> None:
        if self._output_dir.exists():
            return

        self._output_dir.mkdir(parents=True, exist_ok=True)
        # Не на всех файловых системах права можно выставить; логи важнее.
        with suppress(OSError):
            self._output_dir.chmod(dir_mode)

    def _fixtures(self) -> TextIO:
        """Файл фикстур открывается один раз и остаётся открытым до `close()`.

        Повторное открытие обнуляло бы уже записанные логи.
        """
        if self._fixtures_stream is None:
            self._fixtures_stream = self._open(self._fixtures_path, append=False)
        return self._fixtures_stream

    def _reserve_path(self, test_name: str) -> Path:
        """Подобрать незанятое имя файла, добавляя числовой суффикс при повторе."""
        slug = slugify(test_name)
        if self._name_suffix:
            # Разные процессы пишут в разные файлы, даже если имена тестов совпали.
            slug = f"{slug}.{self._name_suffix}"

        attempt = self._used_names.get(slug, 0) + 1
        self._used_names[slug] = attempt

        filename = f"{slug}.log" if attempt == 1 else f"{slug}.{attempt}.log"
        path = self._output_dir / filename

        # slugify исключает разделители пути, так что выход за output_dir невозможен.
        # Проверка защищает от регрессии в slugify.
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
