from __future__ import annotations

import io
import tarfile
import zipfile
from typing import TYPE_CHECKING, cast

import pytest
from assertpy import assert_that

from scripts.skills import validate_catalog, validate_skills
from scripts.workspace import Package

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def contents() -> dict[str, bytes]:
    return {
        "http-client-usage/SKILL.md": b"---\nname: http-client-usage\ndescription: HTTP requests\n---\n",
        "http-client-usage/references/options.md": "# Параметры HTTP\n".encode(),
    }


@pytest.fixture()
def package(tmp_path: Path, contents: dict[str, bytes]) -> Package:
    root = tmp_path / "repository"
    package = Package(root / "packages" / "http-client", "cloudru-qa-http-client", "1.0.0")
    source = root / ".agents" / "skills"
    for name, content in contents.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    links = package.path / ".agents" / "skills"
    links.mkdir(parents=True)
    (links / "http-client-usage").symlink_to(source / "http-client-usage", target_is_directory=True)
    return package


@pytest.fixture(params=["wheel", "sdist"])
def artifact(request: pytest.FixtureRequest, package: Package, tmp_path: Path) -> Path:
    name = package.wheel if cast("str", request.param) == "wheel" else package.sdist
    return tmp_path / name


def _write_artifact(artifact: Path, package: Package, contents: dict[str, bytes]) -> None:
    if artifact.suffix == ".whl":
        prefix = f"{package.module}/.agents/skills"
        with zipfile.ZipFile(artifact, "w") as archive:
            for name, content in contents.items():
                archive.writestr(f"{prefix}/{name}", content)
        return
    prefix = f"{package.sdist.removesuffix('.tar.gz')}/.agents/skills"
    with tarfile.open(artifact, "w:gz") as archive:
        for name, content in contents.items():
            member = tarfile.TarInfo(f"{prefix}/{name}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def test_verifies_skill_and_all_reference_contents(
    package: Package,
    artifact: Path,
    contents: dict[str, bytes],
) -> None:
    _write_artifact(artifact, package, contents)

    assert_that(validate_skills(package, artifact)).is_equal_to(len(contents))


def test_rejects_missing_skill(package: Package, artifact: Path) -> None:
    _write_artifact(artifact, package, {})

    with pytest.raises(ValueError, match=r"SKILL\.md"):
        validate_skills(package, artifact)


def test_rejects_missing_reference(package: Package, artifact: Path, contents: dict[str, bytes]) -> None:
    contents.pop("http-client-usage/references/options.md")
    _write_artifact(artifact, package, contents)

    with pytest.raises(ValueError, match=r"references/options\.md"):
        validate_skills(package, artifact)


def test_rejects_stale_reference(package: Package, artifact: Path, contents: dict[str, bytes]) -> None:
    contents["http-client-usage/references/options.md"] = b"Outdated options"
    _write_artifact(artifact, package, contents)

    with pytest.raises(ValueError, match=r"references/options\.md"):
        validate_skills(package, artifact)


def test_rejects_another_library_skill(package: Package, artifact: Path, contents: dict[str, bytes]) -> None:
    contents["ssh-client-usage/SKILL.md"] = b"SSH connections"
    _write_artifact(artifact, package, contents)

    with pytest.raises(ValueError, match="ssh-client-usage"):
        validate_skills(package, artifact)


def test_rejects_broken_source_link(package: Package, artifact: Path, contents: dict[str, bytes]) -> None:
    (package.path / ".agents" / "skills" / "http-client-usage").resolve().rename(package.path / "moved")
    _write_artifact(artifact, package, contents)

    with pytest.raises(FileNotFoundError):
        validate_skills(package, artifact)


def test_accepts_package_without_skills(package: Package, artifact: Path) -> None:
    (package.path / ".agents" / "skills" / "http-client-usage").unlink()
    _write_artifact(artifact, package, {})

    assert_that(validate_skills(package, artifact)).is_zero()


def test_rejects_sdist_with_external_skill_link(package: Package, tmp_path: Path) -> None:
    artifact = tmp_path / package.sdist
    with tarfile.open(artifact, "w:gz") as archive:
        member = tarfile.TarInfo(f"{package.sdist.removesuffix('.tar.gz')}/.agents/skills/http-client-usage")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../../../.agents/skills/http-client-usage"
        archive.addfile(member)

    with pytest.raises(ValueError, match="regular files"):
        validate_skills(package, artifact)


def test_accounts_for_every_root_skill(package: Package) -> None:
    assert_that(validate_catalog(package.path.parents[1], [package])).is_equal_to(1)


def test_rejects_root_skill_without_package(package: Package) -> None:
    root = package.path.parents[1]
    orphan = root / ".agents" / "skills" / "forgotten-usage" / "SKILL.md"
    orphan.parent.mkdir()
    orphan.write_text("Instructions without a distribution", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one package"):
        validate_catalog(root, [package])


def test_rejects_skill_bundled_in_two_packages(package: Package) -> None:
    sibling = Package(package.path.parent / "http-client-auth", "cloudru-qa-http-client-auth", "1.0.0")
    target = sibling.path / ".agents" / "skills" / "http-client-usage"
    target.parent.mkdir(parents=True)
    target.symlink_to(package.path / ".agents" / "skills" / "http-client-usage", target_is_directory=True)

    with pytest.raises(ValueError, match="exactly one package"):
        validate_catalog(package.path.parents[1], [package, sibling])
