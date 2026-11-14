from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import cast

from scripts.workspace import Package, load_packages

_TAG = re.compile(r"(?P<package>[a-z][a-z0-9]*(?:-[a-z0-9]+)*)/v(?P<version>\d+\.\d+\.\d+)", re.ASCII)


class _Arguments(argparse.Namespace):
    tag: str
    output: Path
    artifacts: Path | None
    destination: Path | None


def select_release(root: Path, tag: str) -> Package:
    """Select a package by tag and validate its version.

    :param root: Repository root.
    :param tag: Tag containing the package name and version.
    :returns: Package to publish.
    :raises ValueError: The tag, name, or version does not match the metadata.
    """
    match = _TAG.fullmatch(tag)
    if match is None:
        message = f"Invalid release tag: {tag}"
        raise ValueError(message)
    packages = {package.path.name: package for package in load_packages(root)}
    name = cast("str", match.group("package"))
    version = cast("str", match.group("version"))
    if name not in packages:
        message = f"Unknown package: {name}"
        raise ValueError(message)
    package = packages[name]
    if version != package.version:
        message = f"Tag version {version} does not match {package.distribution}=={package.version}"
        raise ValueError(message)
    return package


def prepare_artifacts(package: Package, source: Path, destination: Path) -> None:
    """Copy only the wheel and sdist for the selected release.

    :param package: Selected library.
    :param source: Directory containing workspace builds.
    :param destination: New directory for release artifacts.
    :raises FileNotFoundError: The wheel or sdist is missing.
    :raises FileExistsError: The destination directory already exists.
    """
    artifacts = (source / package.wheel, source / package.sdist)
    for artifact in artifacts:
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
    destination.mkdir()
    for artifact in artifacts:
        shutil.copyfile(artifact, destination / artifact.name)


def main() -> None:
    """Write the selected release parameters to a GitHub Actions output file."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("tag")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args(namespace=_Arguments())
    root = Path(__file__).resolve().parents[1]
    package = select_release(root, args.tag)
    if args.artifacts is not None and args.destination is not None:
        prepare_artifacts(package, args.artifacts, args.destination)
    elif args.artifacts is not None or args.destination is not None:
        parser.error("--artifacts and --destination must be used together")
    output = args.output
    with output.open("a", encoding="utf-8") as stream:
        stream.write(f"package={package.distribution}\n")
        stream.write(f"directory={package.path.relative_to(root).as_posix()}\n")
        stream.write(f"version={package.version}\n")


if __name__ == "__main__":
    main()
