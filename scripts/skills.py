from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.workspace import Package, load_packages

if TYPE_CHECKING:
    from collections.abc import Sequence


class _Arguments(argparse.Namespace):
    directory: Path


def validate_catalog(root: Path, packages: Sequence[Package]) -> int:
    """Check that each root skill is bundled with exactly one package.

    :param root: Repository root.
    :param packages: Workspace libraries.
    :returns: Number of bundled skills.
    :raises ValueError: A skill is missing, duplicated, or outside the root catalog.
    """
    catalog = {path.parent.resolve() for path in (root / ".agents" / "skills").glob("*/SKILL.md")}
    sources = [path.resolve() for package in packages for path in _skill_directories(package)]
    if set(sources) != catalog or len(sources) != len(catalog):
        message = "Each root skill must be bundled with exactly one package"
        raise ValueError(message)
    return len(catalog)


def validate_skills(package: Package, artifact: Path) -> int:
    """Compare skill files in a distribution against the root sources.

    :param package: Workspace library.
    :param artifact: Wheel or sdist.
    :returns: Number of checked skill and reference files.
    :raises FileNotFoundError: A source skill link is broken.
    :raises ValueError: Files are missing, changed, added, or left as symbolic links.
    """
    expected = _source_contents(package)
    prefix = f"{package.module}/" if artifact.suffix == ".whl" else ""
    expected = {f"{prefix}.agents/skills/{name}": content for name, content in expected.items()}
    actual = _archive_contents(artifact)
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        unexpected = sorted(actual.keys() - expected.keys())
        changed = sorted(name for name in expected.keys() & actual.keys() if expected[name] != actual[name])
        message = f"{artifact.name}: missing={missing}, unexpected={unexpected}, changed={changed}"
        raise ValueError(message)
    return len(actual)


def main() -> None:
    """Validate skill contents in all wheels and sdists in the build directory."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(namespace=_Arguments())
    root = Path(__file__).resolve().parents[1]
    packages = load_packages(root)
    validate_catalog(root, packages)
    for package in packages:
        validate_skills(package, args.directory / package.wheel)
        validate_skills(package, args.directory / package.sdist)


def _skill_directories(package: Package) -> tuple[Path, ...]:
    return tuple(sorted((package.path / ".agents" / "skills").glob("*")))


def _source_contents(package: Package) -> dict[str, bytes]:
    contents = {}
    for skill in _skill_directories(package):
        if not (skill / "SKILL.md").is_file():
            raise FileNotFoundError(skill / "SKILL.md")
        for path in sorted(skill.rglob("*")):
            if path.is_file():
                contents[f"{skill.name}/{path.relative_to(skill).as_posix()}"] = path.read_bytes()
    return contents


def _archive_contents(artifact: Path) -> dict[str, bytes]:
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as wheel:
            return {
                name: wheel.read(name)
                for name in wheel.namelist()
                if ".agents/skills/" in name and not name.endswith("/")
            }
    contents = {}
    with tarfile.open(artifact) as sdist:
        for member in sdist.getmembers():
            if ".agents/skills/" not in member.name or member.isdir():
                continue
            if not member.isfile():
                message = f"{artifact.name}: skills must be regular files: {member.name}"
                raise ValueError(message)
            stream = sdist.extractfile(member)
            if stream is not None:
                with stream:
                    contents[member.name.partition("/")[2]] = stream.read()
    return contents


if __name__ == "__main__":
    main()
