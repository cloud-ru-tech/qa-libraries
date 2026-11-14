from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self, TypedDict, cast

from assertpy.assertpy import AssertionBuilder

if TYPE_CHECKING:
    import pytest

    _PathAssertions = AssertionBuilder[Path]
else:
    _PathAssertions = AssertionBuilder

_ENCODING = "utf-8"


class _AllureAttachment(TypedDict):
    name: str
    source: str


class _AllureResult(TypedDict):
    uuid: str
    name: str
    attachments: list[_AllureAttachment]


class _AllureStage(TypedDict):
    attachments: list[_AllureAttachment]


class _AllureContainer(TypedDict):
    afters: list[_AllureStage]
    children: list[str]


@dataclass(frozen=True)
class Run:
    """Nested pytest run result with its artifacts."""

    result: pytest.RunResult
    root: Path
    logs_dir: Path
    allure_dir: Path | None = None


if TYPE_CHECKING:
    _RunAssertions = AssertionBuilder[Run]
else:
    _RunAssertions = AssertionBuilder


def run_pytest(
    pytester: pytest.Pytester,
    *args: str,
    allure_dir: Path | None = None,
    in_subprocess: bool = False,
) -> Run:
    """Run nested pytest and collect its artifacts."""
    arguments = [
        "-p",
        "no:logging_context",
        "-p",
        "logging_context.plugin",
        "-p",
        "pytest_asyncio.plugin",
        "-o",
        "asyncio_default_fixture_loop_scope=function",
        *args,
    ]
    if "-n" in args:
        arguments.extend(["-p", "xdist.plugin"])
    if "--reruns" in args:
        arguments.extend(["-p", "pytest_rerunfailures"])
    if allure_dir is not None:
        arguments.extend(["-p", "allure_pytest.plugin", f"--alluredir={allure_dir}"])

    return Run(
        result=pytester.runpytest_subprocess(*arguments) if in_subprocess else pytester.runpytest(*arguments),
        root=pytester.path,
        logs_dir=pytester.path / "logs",
        allure_dir=allure_dir,
    )


class LogsAssertions(_PathAssertions):
    """Assertions about the run log file directory."""

    def is_empty(self) -> Self:
        """Check that the plugin created no log files."""
        files = self._filenames()
        if files:
            self.error(f"Expected no log files, but found <{files}>")
        return self

    def has_log_files(self, *expected: str) -> Self:
        """Check that the directory contains exactly the listed files."""
        actual = self._filenames()
        if actual != sorted(expected):
            self.error(f"Expected log files <{sorted(expected)}>, but found <{actual}>")
        return self

    def has_log(self, filename: str) -> Self:
        """Check that a log file with this name was created."""
        if not self._path(filename).exists():
            self.error(f"Expected log file <{filename}>, but found only <{self._filenames()}>")
        return self

    def has_log_with_lines(self, filename: str, *expected: str) -> Self:
        """Check that the log file contains exactly these lines in this order."""
        actual = self._lines(filename)
        if actual != list(expected):
            self.error(f"Expected lines of <{filename}> to be <{list(expected)}>, but were <{actual}>")
        return self

    def has_log_containing(self, filename: str, fragment: str) -> Self:
        """Check that the log file contains a fragment."""
        content = self._content(filename)
        if fragment not in content:
            self.error(f"Expected <{filename}> to contain <{fragment}>, but was <{content}>")
        return self

    def has_log_without(self, filename: str, *fragments: str) -> Self:
        """Check that the log file contains none of these fragments, such as logs from other tests."""
        content = self._content(filename)
        leaked = [fragment for fragment in fragments if fragment in content]
        if leaked:
            self.error(f"Expected <{filename}> not to contain <{leaked}>, but was <{content}>")
        return self

    def has_logs(self, **expected: str) -> Self:
        """Each listed file (without extension) contains exactly the specified text."""
        mismatched = {
            name: (expected_content, self._content(f"{name}.log"))
            for name, expected_content in expected.items()
            if self._content(f"{name}.log") != expected_content
        }
        if mismatched:
            self.error(f"Log files do not match, «expected -> actual»: <{mismatched}>")
        return self

    def has_test_logs(self, **expected: str) -> Self:
        """Like `has_logs`, but independent of worker suffixes in filenames.

        Under xdist, filenames include the worker id, and which test runs on which
        worker is undefined.
        """
        mismatched = {}
        for name, expected_content in expected.items():
            matched = self._files_of_test(name)
            if len(matched) != 1 or self._content(matched[0]) != expected_content:
                mismatched[name] = (expected_content, [(f, self._content(f)) for f in matched])
        if mismatched:
            self.error(f"Test logs do not match, «expected -> actual»: <{mismatched}>")
        return self

    def _files_of_test(self, name: str) -> list[str]:
        return [
            filename
            for filename in self._filenames()
            if filename == f"{name}.log" or (filename.startswith(f"{name}.") and filename.endswith(".log"))
        ]

    def has_log_count(self, expected: int) -> Self:
        """Check that the directory contains exactly this many log files."""
        actual = self._filenames()
        if len(actual) != expected:
            self.error(f"Expected <{expected}> log files, but found <{len(actual)}>: <{actual}>")
        return self

    def has_log_in_every_file_containing(self, fragment: str) -> Self:
        """Every log file in the directory contains the fragment."""
        names = self._filenames()
        if not names:
            self.error(f"Expected log files containing <{fragment}>, but the directory has none")
        missing = [name for name in names if fragment not in self._content(name)]
        if missing:
            self.error(f"Expected every log file to contain <{fragment}>, but <{missing}> did not")
        return self

    def has_json_log(self, filename: str, *expected: dict[str, object]) -> Self:
        """Check that the log file is JSON Lines with exactly these records."""
        actual = self._json_records(filename)
        if actual != list(expected):
            self.error(f"Expected JSON records of <{filename}> to be <{list(expected)}>, but were <{actual}>")
        return self

    def has_json_log_field(self, filename: str, field: str, expected: object) -> Self:
        """Check that the first JSON record in the file contains a field with the expected value."""
        records = self._json_records(filename)
        if not records:
            self.error(f"Expected <{filename}> to contain JSON records, but it was empty")
        actual = records[0].get(field)
        if actual != expected:
            self.error(
                f"Expected field <{field}> of <{filename}> to be <{expected}>, but was <{actual}> in <{records[0]}>"
            )
        return self

    def has_json_log_events(self, filename: str, *expected: str) -> Self:
        """JSON record events from the file in arrival order."""
        actual = [record.get("event") for record in self._json_records(filename)]
        if actual != list(expected):
            self.error(f"Expected events of <{filename}> to be <{list(expected)}>, but were <{actual}>")
        return self

    def has_log_unreadable_by_others(self, filename: str) -> Self:
        """Check that the log file is unreadable by group and others."""
        mode = stat.S_IMODE(self._path(filename).stat().st_mode)
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            self.error(f"Expected <{filename}> to be private, but mode was <{oct(mode)}>")
        return self

    def is_unreadable_by_others(self) -> Self:
        """Check that the log directory itself is unreadable by group and others."""
        mode = stat.S_IMODE(self._dir().stat().st_mode)
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            self.error(f"Expected <{self._dir()}> to be private, but mode was <{oct(mode)}>")
        return self

    def _dir(self) -> Path:
        return Path(self.val)

    def _path(self, filename: str) -> Path:
        return self._dir() / filename

    def _filenames(self) -> list[str]:
        directory = self._dir()
        if not directory.exists():
            return []
        return sorted(path.name for path in directory.iterdir() if path.is_file())

    def _content(self, filename: str) -> str:
        path = self._path(filename)
        if not path.exists():
            self.error(f"Expected log file <{filename}>, but found only <{self._filenames()}>")
        return path.read_text(encoding=_ENCODING)

    def _lines(self, filename: str) -> list[str]:
        return [line for line in self._content(filename).splitlines() if line.strip()]

    def _json_records(self, filename: str) -> list[dict[str, object]]:
        return [cast("dict[str, object]", json.loads(line)) for line in self._lines(filename)]


class AllureAssertions(_PathAssertions):
    """Assertions about attachments in the allure-results directory."""

    def has_attachment(self, test_name: str, attachment: str, expected: str) -> Self:
        """Check that the test has an attachment with this name and content."""
        attachments = self._attachments_of(test_name)
        if attachment not in attachments:
            self.error(
                f"Expected test <{test_name}> to have attachment <{attachment}>, but had <{sorted(attachments)}>"
            )
        if attachments[attachment] != expected:
            self.error(
                f"Expected attachment <{attachment}> of <{test_name}> to be <{expected}>, "
                f"but was <{attachments[attachment]}>"
            )
        return self

    def has_no_attachment(self, test_name: str, attachment: str) -> Self:
        """Check that the test has no attachment with this name."""
        attachments = self._attachments_of(test_name)
        if attachment in attachments:
            self.error(f"Expected test <{test_name}> not to have attachment <{attachment}>, but it had it")
        return self

    def has_attachment_for_every_test(self, attachment: str, expected: str) -> Self:
        """Every test in the run has this attachment with this content."""
        per_test = self._per_test()
        if not per_test:
            self.error(f"Expected tests with attachment <{attachment}>, but no test results were found")
        mismatched = {
            name: attachments.get(attachment)
            for name, attachments in per_test.items()
            if attachments.get(attachment) != expected
        }
        if mismatched:
            self.error(f"Expected every test to have attachment <{attachment}>=<{expected}>, but got <{mismatched}>")
        return self

    def _dir(self) -> Path:
        return Path(self.val)

    def _attachments_of(self, test_name: str) -> dict[str, str]:
        per_test = self._per_test()
        if test_name not in per_test:
            self.error(f"Expected results for test <{test_name}>, but found only <{sorted(per_test)}>")
        return per_test[test_name]

    def _per_test(self) -> dict[str, dict[str, str]]:
        results = {
            data["uuid"]: data
            for data in (
                cast("_AllureResult", json.loads(path.read_text(encoding=_ENCODING)))
                for path in self._dir().glob("*-result.json")
            )
        }

        per_test: dict[str, dict[str, str]] = {
            data["name"]: {item["name"]: self._body(item) for item in data.get("attachments", [])}
            for data in results.values()
        }
        self._add_fixture_attachments(results, per_test)
        return per_test

    def _add_fixture_attachments(
        self,
        results: dict[str, _AllureResult],
        per_test: dict[str, dict[str, str]],
    ) -> None:
        """Allure places attachments created during fixture teardown in the fixture container."""
        for path in self._dir().glob("*-container.json"):
            container = cast("_AllureContainer", json.loads(path.read_text(encoding=_ENCODING)))
            for stage in container.get("afters", []):
                for item in stage.get("attachments", []):
                    for child in container.get("children", []):
                        if child in results:
                            per_test[results[child]["name"]][item["name"]] = self._body(item)

    def _body(self, attachment: _AllureAttachment) -> str:
        source: str = attachment["source"]
        return (self._dir() / source).read_text(encoding=_ENCODING)


class RunAssertions(_RunAssertions):
    """Assertions about the run outcome, log files, and Allure attachments.

    Facade over `LogsAssertions` and `AllureAssertions` so tests can use one
    assertion about both the run outcome and its recorded artifacts.
    """

    def passed(self, count: int) -> Self:
        """Check that the run finished with exactly this many passed tests."""
        self._run().result.assert_outcomes(passed=count)
        return self

    def failed(self, count: int) -> Self:
        """Check that the run finished with exactly this many failed tests."""
        self._run().result.assert_outcomes(failed=count)
        return self

    def errored(self, count: int) -> Self:
        """Check that the run finished with exactly this many errors."""
        self._run().result.assert_outcomes(errors=count)
        return self

    def was_stopped(self) -> Self:
        """Check that the run did not complete: pytest exited with a nonzero code."""
        code = self._run().result.ret
        if code == 0:
            self.error("Expected pytest to stop with a non-zero exit code, but it succeeded")
        return self

    def reports_error(self, pattern: str) -> Self:
        """Check that the run stderr contains a line matching the pattern."""
        self._run().result.stderr.fnmatch_lines([pattern])
        return self

    def is_empty(self) -> Self:
        """Check that the run created no log files."""
        self._logs().is_empty()
        return self

    def has_log(self, filename: str) -> Self:
        self._logs().has_log(filename)
        return self

    def has_log_count(self, expected: int) -> Self:
        self._logs().has_log_count(expected)
        return self

    def has_logs(self, **expected: str) -> Self:
        self._logs().has_logs(**expected)
        return self

    def has_test_logs(self, **expected: str) -> Self:
        self._logs().has_test_logs(**expected)
        return self

    def has_log_with_lines(self, filename: str, *expected: str) -> Self:
        self._logs().has_log_with_lines(filename, *expected)
        return self

    def has_log_containing(self, filename: str, fragment: str) -> Self:
        self._logs().has_log_containing(filename, fragment)
        return self

    def has_log_without(self, filename: str, *fragments: str) -> Self:
        self._logs().has_log_without(filename, *fragments)
        return self

    def has_log_in_every_file_containing(self, fragment: str) -> Self:
        self._logs().has_log_in_every_file_containing(fragment)
        return self

    def has_json_log(self, filename: str, *expected: dict[str, object]) -> Self:
        self._logs().has_json_log(filename, *expected)
        return self

    def has_json_log_field(self, filename: str, field: str, expected: object) -> Self:
        self._logs().has_json_log_field(filename, field, expected)
        return self

    def has_json_log_events(self, filename: str, *expected: str) -> Self:
        self._logs().has_json_log_events(filename, *expected)
        return self

    def has_attachment(self, test_name: str, attachment: str, expected: str) -> Self:
        self._allure().has_attachment(test_name, attachment, expected)
        return self

    def has_no_attachment(self, test_name: str, attachment: str) -> Self:
        self._allure().has_no_attachment(test_name, attachment)
        return self

    def has_attachment_for_every_test(self, attachment: str, expected: str) -> Self:
        self._allure().has_attachment_for_every_test(attachment, expected)
        return self

    def wrote_no_logs_outside_logs_dir(self) -> Self:
        """Check that the run created no log files outside the log directory."""
        run = self._run()
        logs_dir = run.logs_dir.resolve()
        stray = [
            str(path.relative_to(run.root))
            for path in run.root.rglob("*.log")
            if logs_dir not in path.resolve().parents
        ]
        if stray:
            self.error(f"Expected no log files outside <{run.logs_dir}>, but found <{stray}>")
        return self

    def in_launch(self, launch_id: str) -> RunAssertions:
        """Continue checking logs in the run subdirectory."""
        run = self._run()
        return RunAssertions(Run(run.result, run.root, run.logs_dir / launch_id, run.allure_dir))

    def _run(self) -> Run:
        run: Run = self.val
        return run

    def _logs(self) -> LogsAssertions:
        return LogsAssertions(self._run().logs_dir)

    def _allure(self) -> AllureAssertions:
        allure_dir = self._run().allure_dir
        if allure_dir is None:
            self.error("Expected the run to produce allure results, but no allure directory was requested")
        return AllureAssertions(cast("Path", allure_dir))


def assert_logs(logs_dir: Path) -> LogsAssertions:
    """Start checking the log file directory."""
    return LogsAssertions(logs_dir)


def assert_allure(allure_dir: Path) -> AllureAssertions:
    """Start checking the allure-results directory."""
    return AllureAssertions(allure_dir)


def assert_run(run: Run) -> RunAssertions:
    """Start checking the pytest run."""
    return RunAssertions(run)
