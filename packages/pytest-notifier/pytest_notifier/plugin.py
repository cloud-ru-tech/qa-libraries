import contextlib
from typing import TYPE_CHECKING, cast

import pytest
from _pytest._code.code import ExceptionRepr

from .models import TestFailureInfo, TestResults
from .notifiers import NOTIFIER_REGISTRY, NotifierBase
from .settings import Settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from _pytest.terminal import TerminalReporter


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Pytest hook that sends a result summary to all active channels."""
    settings = Settings()
    results = extract_test_results(session, exitstatus)

    if results.failed == 0 and results.error == 0:
        return

    notifiers = get_active_notifiers(settings)

    for notifier in notifiers:
        with contextlib.suppress(Exception):
            notifier.send(results)


def extract_test_results(session: pytest.Session, exitstatus: int) -> TestResults:
    """Extract results from pytest.Session into an independent structure."""
    tr = cast("TerminalReporter | None", session.config.pluginmanager.get_plugin("terminalreporter"))

    passed = failed = error = skipped = xfailed = xpassed = 0
    collected = session.testscollected
    failures: list[TestFailureInfo] = []
    errors: list[TestFailureInfo] = []

    if tr is not None:
        stats = cast("Mapping[str, Sequence[pytest.TestReport]]", tr.stats)
        passed = len(stats.get("passed", []))
        failed = len(stats.get("failed", []))
        error = len(stats.get("error", []))
        skipped = len(stats.get("skipped", []))
        xfailed = len(stats.get("xfailed", []))
        xpassed = len(stats.get("xpassed", []))

        failures.extend(extract_failure_info(report) for report in stats.get("failed", []))

        errors.extend(extract_failure_info(report) for report in stats.get("error", []))

    exitstatus_text = exitstatus_to_text(exitstatus)

    return TestResults(
        collected=collected,
        passed=passed,
        failed=failed,
        error=error,
        skipped=skipped,
        xfailed=xfailed,
        xpassed=xpassed,
        exitstatus=exitstatus,
        exitstatus_text=exitstatus_text,
        failures=failures,
        errors=errors,
    )


def get_active_notifiers(settings: Settings) -> list[NotifierBase]:
    """Return active notifiers based on the destinations flags."""
    notifiers = []

    for destination, notifier_class in NOTIFIER_REGISTRY.items():
        if settings.destinations & destination:
            notifier = notifier_class(settings)
            if notifier.is_enabled():
                notifiers.append(notifier)

    return notifiers


def extract_failure_info(report: pytest.TestReport) -> TestFailureInfo:
    """Extract error information from TestReport."""
    file_path, _line, test_name = report.location
    error_message = get_short_error_message(report)
    traceback = report.longreprtext

    return TestFailureInfo(
        nodeid=report.nodeid,
        name=test_name,
        file_path=file_path,
        error_message=error_message,
        traceback=traceback,
        duration=report.duration,
    )


def get_short_error_message(report: pytest.TestReport) -> str:
    """Extract a short error message from the report."""
    longrepr = report.longrepr

    if longrepr is None:
        return "Unknown error"

    if isinstance(longrepr, str):
        return longrepr[:200]

    reprcrash = longrepr.reprcrash if isinstance(longrepr, ExceptionRepr) else None
    if reprcrash:
        message = reprcrash.message
        if message:
            return message[:200]

    longreprtext = report.longreprtext
    if longreprtext:
        first_line = longreprtext.split("\n")[0]
        return first_line[:200]

    return "Unknown error"


def exitstatus_to_text(exitstatus: int) -> str:
    """Convert a pytest exit code to text."""
    try:
        code = pytest.ExitCode(exitstatus)
    except ValueError:
        return str(exitstatus)
    else:
        return code.name
