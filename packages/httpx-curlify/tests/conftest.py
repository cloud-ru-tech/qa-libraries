import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode


class TextSnapshotExtension(SingleFileSnapshotExtension):
    """Extension for creating snapshots as separate text files."""

    _file_extension = "txt"
    _write_mode = WriteMode.TEXT


@pytest.fixture()
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Fixture for text snapshots."""
    return snapshot.use_extension(TextSnapshotExtension)
