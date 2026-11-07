from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast


class _Arguments(argparse.Namespace):
    directory: Path


def count_findings(report: Path) -> int:
    """Проверить SARIF-отчёт и посчитать находки.

    :param report: файл SARIF, созданный CodeQL
    :returns: количество находок во всех запусках анализа
    :raises ValueError: отчёт неполный или имеет неподдерживаемую структуру
    """
    document = cast("dict[str, object]", json.loads(report.read_text(encoding="utf-8")))
    if document.get("version") != "2.1.0":
        message = f"Unsupported SARIF version: {report}"
        raise ValueError(message)
    runs = cast("list[dict[str, object]]", document.get("runs"))
    if not runs:
        message = f"No analysis runs in {report}"
        raise ValueError(message)
    count = 0
    for run in runs:
        _check_invocations(run, report)
        if "results" not in run:
            message = f"Missing analysis results in {report}"
            raise ValueError(message)
        value = run["results"]
        if not isinstance(value, list):
            message = f"Invalid analysis results in {report}"
            raise TypeError(message)
        results = cast("list[object]", value)
        count += len(results)
    return count


def main() -> None:
    """Завершить CI с ошибкой при находках CodeQL или отсутствии отчётов."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(namespace=_Arguments())
    reports = sorted(args.directory.glob("*.sarif"))
    if not reports:
        message = f"No SARIF reports in {args.directory}"
        raise ValueError(message)
    findings = sum(count_findings(report) for report in reports)
    if findings:
        message = f"CodeQL reported {findings} findings"
        raise ValueError(message)


def _check_invocations(run: dict[str, object], report: Path) -> None:
    invocations = cast("list[dict[str, object]]", run.get("invocations", []))
    for invocation in invocations:
        if invocation.get("executionSuccessful") is False:
            message = f"CodeQL analysis was unsuccessful: {report}"
            raise ValueError(message)
        for category in ("toolExecutionNotifications", "toolConfigurationNotifications"):
            notifications = cast("list[dict[str, object]]", invocation.get(category, []))
            if any(notification.get("level") == "error" for notification in notifications):
                message = f"CodeQL reported diagnostic errors: {report}"
                raise ValueError(message)


if __name__ == "__main__":
    main()
