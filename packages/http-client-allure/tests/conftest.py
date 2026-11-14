from pathlib import Path

import allure
import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.single_file import SingleFileAmberSnapshotExtension
from syrupy.location import PyTestLocation

from .allure_recorder import Report
from .config import SRC_ROOT


class CustomSnapshotDirectoryExtension(SingleFileAmberSnapshotExtension):
    """Syrupy extension that overrides the snapshot directory."""

    SNAPSHOTS_DIRECTORY = SRC_ROOT / "data" / "snapshots"

    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return str(Path(test_location.filepath).parent.joinpath(cls.SNAPSHOTS_DIRECTORY))


@pytest.fixture()
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.with_defaults(extension_class=CustomSnapshotDirectoryExtension)


@pytest.fixture()
def report(monkeypatch: pytest.MonkeyPatch) -> Report:
    """Replace Allure with a fake that records steps and attachments."""
    recorder = Report()
    monkeypatch.setattr(allure, "step", recorder.step)
    monkeypatch.setattr(allure, "attach", recorder.attach)

    return recorder
