from pathlib import Path

import allure
import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.single_file import SingleFileAmberSnapshotExtension
from syrupy.location import PyTestLocation

from .allure_recorder import Report
from .config import SRC_ROOT


class CustomSnapshotDirectoryExtension(SingleFileAmberSnapshotExtension):
    """Расширение syrupy для переопределения директории со снепшотами."""

    SNAPSHOTS_DIRECTORY = SRC_ROOT / "data" / "snapshots"

    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return str(Path(test_location.filepath).parent.joinpath(cls.SNAPSHOTS_DIRECTORY))


@pytest.fixture()
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.with_defaults(extension_class=CustomSnapshotDirectoryExtension)


@pytest.fixture()
def report(monkeypatch: pytest.MonkeyPatch) -> Report:
    """Подменить Allure фейком, который запоминает шаги и вложения."""
    recorder = Report()
    monkeypatch.setattr(allure, "step", recorder.step)
    monkeypatch.setattr(allure, "attach", recorder.attach)

    return recorder
