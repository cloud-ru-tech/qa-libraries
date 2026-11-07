import json
from json import JSONDecodeError
from pathlib import Path

import pytest
from assertpy import assert_that

from scripts.security import count_findings


def test_accepts_sarif_without_findings(tmp_path: Path) -> None:
    report = tmp_path / "python.sarif"
    document: dict[str, object] = {"version": "2.1.0", "runs": [{"results": []}]}
    report.write_text(json.dumps(document), encoding="utf-8")

    assert_that(count_findings(report)).is_zero()


def test_counts_findings_across_sarif_runs(tmp_path: Path) -> None:
    report = tmp_path / "python.sarif"
    document: dict[str, object] = {
        "version": "2.1.0",
        "runs": [{"results": [{"ruleId": "py/unsafe"}]}, {"results": [{"ruleId": "py/injection"}]}],
    }
    report.write_text(json.dumps(document), encoding="utf-8")

    assert_that(count_findings(report)).is_equal_to(2)


def test_rejects_report_without_runs(tmp_path: Path) -> None:
    report = tmp_path / "python.sarif"
    document: dict[str, object] = {"version": "2.1.0", "runs": []}
    report.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="No analysis runs"):
        count_findings(report)


def test_rejects_missing_analysis_results(tmp_path: Path) -> None:
    report = tmp_path / "python.sarif"
    document: dict[str, object] = {"version": "2.1.0", "runs": [{}]}
    report.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing analysis results"):
        count_findings(report)


def test_rejects_invalid_report_json(tmp_path: Path) -> None:
    report = tmp_path / "python.sarif"
    report.write_text("not a report", encoding="utf-8")

    with pytest.raises(JSONDecodeError):
        count_findings(report)


def test_rejects_unsuccessful_analysis_even_without_findings(tmp_path: Path) -> None:
    report = tmp_path / "python.sarif"
    document: dict[str, object] = {
        "version": "2.1.0",
        "runs": [{"results": [], "invocations": [{"executionSuccessful": False}]}],
    }
    report.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="unsuccessful"):
        count_findings(report)


@pytest.mark.parametrize("kind", ["toolExecutionNotifications", "toolConfigurationNotifications"])
def test_rejects_error_notifications_even_when_execution_succeeds(tmp_path: Path, kind: str) -> None:
    report = tmp_path / "python.sarif"
    document: dict[str, object] = {
        "version": "2.1.0",
        "runs": [{"results": [], "invocations": [{"executionSuccessful": True, kind: [{"level": "error"}]}]}],
    }
    report.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="diagnostic errors"):
        count_findings(report)
