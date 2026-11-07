from pathlib import Path

import pytest
from assertpy import assert_that

from scripts.release import prepare_artifacts, select_release


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    package = tmp_path / "packages" / "http-client"
    package.mkdir(parents=True)
    (package / "pyproject.toml").write_text(
        '[project]\nname = "cloudru-qa-http-client"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_selects_distribution_for_package_tag(workspace: Path) -> None:
    release = select_release(workspace, "http-client/v1.0.0")

    assert_that(release.distribution).is_equal_to("cloudru-qa-http-client")


def test_preserves_release_version(workspace: Path) -> None:
    release = select_release(workspace, "http-client/v1.0.0")

    assert_that(release.version).is_equal_to("1.0.0")


@pytest.mark.parametrize(
    "tag",
    ["v1.0.0", "http-client/1.0.0", "http-client/v1.0", "../v1.0.0", "http-client/v1.0.0/extra"],
)
def test_rejects_malformed_release_tags(workspace: Path, tag: str) -> None:
    with pytest.raises(ValueError, match="Invalid release tag"):
        select_release(workspace, tag)


def test_rejects_unknown_packages(workspace: Path) -> None:
    with pytest.raises(ValueError, match="Unknown package"):
        select_release(workspace, "missing-client/v1.0.0")


def test_rejects_version_mismatch(workspace: Path) -> None:
    with pytest.raises(ValueError, match="does not match"):
        select_release(workspace, "http-client/v1.0.1")


def test_rejects_package_name_mismatch(workspace: Path) -> None:
    manifest = workspace / "packages" / "http-client" / "pyproject.toml"
    manifest.write_text('[project]\nname = "another-package"\nversion = "1.0.0"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Distribution name"):
        select_release(workspace, "http-client/v1.0.0")


@pytest.fixture()
def distributions(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / "cloudru_qa_http_client-1.0.0-py3-none-any.whl").write_bytes(b"wheel")
    (directory / "cloudru_qa_http_client-1.0.0.tar.gz").write_bytes(b"source")
    (directory / "cloudru_qa_http_client_auth-1.0.0-py3-none-any.whl").write_bytes(b"another wheel")
    return directory


def test_prepares_only_selected_distribution(workspace: Path, distributions: Path, tmp_path: Path) -> None:
    package = select_release(workspace, "http-client/v1.0.0")
    destination = tmp_path / "release"

    prepare_artifacts(package, distributions, destination)

    assert_that(tuple(destination.iterdir())).contains_only(
        destination / "cloudru_qa_http_client-1.0.0-py3-none-any.whl",
        destination / "cloudru_qa_http_client-1.0.0.tar.gz",
    )


def test_rejects_missing_release_artifact(workspace: Path, distributions: Path, tmp_path: Path) -> None:
    package = select_release(workspace, "http-client/v1.0.0")
    (distributions / "cloudru_qa_http_client-1.0.0.tar.gz").unlink()

    with pytest.raises(FileNotFoundError):
        prepare_artifacts(package, distributions, tmp_path / "release")


def test_refuses_to_mix_artifacts_with_existing_destination(
    workspace: Path, distributions: Path, tmp_path: Path
) -> None:
    package = select_release(workspace, "http-client/v1.0.0")
    destination = tmp_path / "release"
    destination.mkdir()

    with pytest.raises(FileExistsError):
        prepare_artifacts(package, distributions, destination)
