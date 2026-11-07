import runpy
import sys
from pathlib import Path

import pytest
from assertpy import assert_that

import scripts.wheels
from scripts.wheels import local_overrides
from scripts.workspace import Package


@pytest.fixture()
def directory(tmp_path: Path) -> Path:
    path = tmp_path / "dist"
    path.mkdir()
    return path


@pytest.fixture()
def packages(tmp_path: Path, directory: Path) -> tuple[Package, ...]:
    packages = (
        Package(tmp_path / "packages" / "http-client", "cloudru-qa-http-client", "1.0.0"),
        Package(tmp_path / "packages" / "http-client-allure", "cloudru-qa-http-client-allure", "1.2.0"),
    )
    for package in packages:
        (directory / package.wheel).touch()
    return packages


def test_pins_every_library_to_its_built_wheel(packages: tuple[Package, ...], directory: Path) -> None:
    overrides = local_overrides(packages, directory)

    client = directory / "cloudru_qa_http_client-1.0.0-py3-none-any.whl"
    allure = directory / "cloudru_qa_http_client_allure-1.2.0-py3-none-any.whl"
    assert_that(overrides.splitlines()).is_equal_to(
        [
            f"cloudru-qa-http-client @ {client.as_uri()}",
            f"cloudru-qa-http-client-allure @ {allure.as_uri()}",
        ]
    )


def test_rejects_library_without_built_wheel(packages: tuple[Package, ...], directory: Path) -> None:
    (directory / packages[1].wheel).unlink()

    with pytest.raises(FileNotFoundError, match="cloudru_qa_http_client_allure"):
        local_overrides(packages, directory)


def test_runs_checks_from_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scripts.wheels", "--help"])

    with pytest.raises(SystemExit, match="0"):
        runpy.run_path(scripts.wheels.__file__, run_name="__main__")
