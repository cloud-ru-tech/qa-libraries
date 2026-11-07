from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class Package:
    """Метаданные библиотеки workspace.

    :param path: каталог библиотеки
    :param distribution: имя дистрибутива в PyPI
    :param version: версия библиотеки
    """

    path: Path
    distribution: str
    version: str

    @property
    def module(self) -> str:
        """Вернуть имя Python-модуля.

        :returns: имя модуля без префикса дистрибутива
        """
        return self.path.name.replace("-", "_")

    @property
    def wheel(self) -> str:
        """Вернуть имя файла wheel.

        :returns: имя wheel чистого Python-пакета
        """
        return f"{self._artifact_prefix}-py3-none-any.whl"

    @property
    def sdist(self) -> str:
        """Вернуть имя архива sdist.

        :returns: имя архива с исходным кодом
        """
        return f"{self._artifact_prefix}.tar.gz"

    @property
    def _artifact_prefix(self) -> str:
        return f"{self.distribution.replace('-', '_')}-{self.version}"


def load_packages(root: Path) -> tuple[Package, ...]:
    """Прочитать метаданные участников workspace.

    :param root: корень репозитория
    :returns: библиотеки в порядке имён каталогов
    :raises ValueError: метаданные не соответствуют соглашениям monorepo
    :raises TypeError: имя или версия не являются строками
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
