from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class Package:
    """Metadata for a workspace library.

    :param path: Library directory.
    :param distribution: Distribution name on PyPI.
    :param version: Library version.
    """

    path: Path
    distribution: str
    version: str

    @property
    def module(self) -> str:
        """Return the Python module name.

        :returns: Module name without the distribution prefix.
        """
        return self.path.name.replace("-", "_")

    @property
    def wheel(self) -> str:
        """Return the wheel filename.

        :returns: Wheel filename for a pure Python package.
        """
        return f"{self._artifact_prefix}-py3-none-any.whl"

    @property
    def sdist(self) -> str:
        """Return the sdist archive filename.

        :returns: Source archive filename.
        """
        return f"{self._artifact_prefix}.tar.gz"

    @property
    def _artifact_prefix(self) -> str:
        return f"{self.distribution.replace('-', '_')}-{self.version}"


def load_packages(root: Path) -> tuple[Package, ...]:
    """Read metadata for workspace members.

    :param root: Repository root.
    :returns: Libraries sorted by directory name.
    :raises ValueError: Metadata does not follow the monorepo conventions.
    :raises TypeError: The name or version is not a string.
    """
    packages = []
    for manifest in sorted((root / "packages").glob("*/pyproject.toml")):
        document = cast("dict[str, dict[str, object]]", tomllib.loads(manifest.read_text(encoding="utf-8")))
        project = document["project"]
        distribution = project["name"]
        version = project["version"]
        if not isinstance(distribution, str) or not isinstance(version, str):
            message = f"Package name and version must be strings: {manifest}"
            raise TypeError(message)
        expected = f"cloudru-qa-{manifest.parent.name}"
        if distribution != expected:
            message = f"Distribution name must be {expected}: {distribution}"
            raise ValueError(message)
        packages.append(Package(manifest.parent, distribution, version))
    return tuple(packages)
