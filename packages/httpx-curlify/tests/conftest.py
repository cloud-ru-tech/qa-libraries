import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode


class TextSnapshotExtension(SingleFileSnapshotExtension):
    """Расширение для создания снепшотов в виде отдельных текстовых файлов."""

    _file_extension = "txt"
    _write_mode = WriteMode.TEXT


@pytest.fixture()
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Фикстура для использования текстовых снепшотов."""
    return snapshot.use_extension(TextSnapshotExtension)
