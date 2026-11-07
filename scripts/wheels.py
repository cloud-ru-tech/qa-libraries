from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.skills import validate_skills
from scripts.workspace import Package, load_packages

if TYPE_CHECKING:
    from collections.abc import Sequence


class _Arguments(argparse.Namespace):
    directory: Path
    uv: str


def local_overrides(packages: Sequence[Package], directory: Path) -> str:
    """Составить overrides uv, которые подставляют собранные wheel вместо версий из PyPI.

    Без них uv может взять библиотеку-зависимость той же версии из PyPI,
    и проверка установит старый опубликованный код вместо собранного.

    :param packages: библиотеки workspace
    :param directory: каталог с собранными wheel
    :returns: содержимое файла overrides, по строке на библиотеку
    :raises FileNotFoundError: wheel библиотеки отсутствует
    """
    lines = []
    for package in packages:
        wheel = directory / package.wheel
        if not wheel.is_file():
            raise FileNotFoundError(wheel)
        lines.append(f"{package.distribution} @ {wheel.resolve().as_uri()}\n")
    return "".join(lines)


def main() -> None:
    """Пересобрать sdist, проверить скиллы и установить каждый wheel в пустое окружение.

    Проверка ловит зависимости, которые библиотека использует, но не объявляет:
    в общем окружении workspace их ставят соседние библиотеки.
    """
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(namespace=_Arguments())
    root = Path(__file__).resolve().parents[1]
    packages = load_packages(root)
    with tempfile.TemporaryDirectory() as temporary:
        workdir = Path(temporary)
        constraints = workdir / "constraints.txt"
        overrides = workdir / "overrides.txt"
        overrides.write_text(local_overrides(packages, args.directory), encoding="utf-8")
        _uv(
            args.uv,
            "export",
            "--locked",
            "--all-packages",
            "--all-extras",
            "--all-groups",
            "--no-emit-workspace",
            "--no-hashes",
            "--output-file",
            str(constraints),
        )
        pins = ("--constraint", str(constraints), "--override", str(overrides))
        for package in packages:
            rebuilt = workdir / "rebuilt" / package.path.name
            _uv(
                args.uv,
                "build",
                "--wheel",
                "--no-sources",
                "--out-dir",
                str(rebuilt),
                str(args.directory / package.sdist),
            )
            validate_skills(package, rebuilt / package.wheel)
            python = _environment(args.uv, workdir / package.path.name)
            _uv(args.uv, "pip", "install", "--python", python, *pins, str(args.directory / package.wheel))
            _uv(args.uv, "pip", "check", "--python", python)
            _run(python, "-I", "-W", "error", "-c", f"import {package.module}")
        python = _environment(args.uv, workdir / "all")
        wheels = [str(args.directory / package.wheel) for package in packages]
        _uv(args.uv, "pip", "install", "--python", python, *pins, *wheels)
        _uv(args.uv, "pip", "check", "--python", python)


def _environment(uv: str, path: Path) -> str:
    _uv(uv, "venv", "--python", sys.executable, str(path))
    return str(path / "bin" / "python")


def _uv(uv: str, *arguments: str) -> None:
    # export дублирует результат в stdout, а он здесь не нужен.
    _run(uv, "--quiet", *arguments, stdout=subprocess.DEVNULL)


def _run(*command: str, stdout: int | None = None) -> None:
    # Команда передаётся списком без shell; аргументы берутся из метаданных workspace.
    subprocess.run(command, check=True, stdout=stdout)  # noqa: S603


if __name__ == "__main__":
    main()
