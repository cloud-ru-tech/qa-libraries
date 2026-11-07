import pytest
from assertpy import assert_that
from pytest_notifier.plugin import exitstatus_to_text, extract_failure_info, get_short_error_message


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (0, "OK"),
        (1, "TESTS_FAILED"),
        (2, "INTERRUPTED"),
        (3, "INTERNAL_ERROR"),
        (4, "USAGE_ERROR"),
        (5, "NO_TESTS_COLLECTED"),
        (71, "71"),
    ],
)
def test_describes_exit_status(status: int, expected: str) -> None:
    assert_that(exitstatus_to_text(status)).is_equal_to(expected)


def test_extracts_test_identity_and_failure_details() -> None:
    report = pytest.TestReport(
        nodeid="suite/test_api.py::test_fetch",
        location=("suite/test_api.py", 18, "test_fetch"),
        keywords=dict[str, object](),
        outcome="failed",
        longrepr="unexpected response",
        when="call",
        duration=0.375,
    )

    failure = extract_failure_info(report)

    assert_that(failure).has_nodeid(report.nodeid).has_name("test_fetch").has_file_path(
        "suite/test_api.py"
    ).has_error_message("unexpected response").has_duration(0.375)


def test_limits_short_failure_message() -> None:
    report = pytest.TestReport(
        "test.py::test_big", ("test.py", 0, "test_big"), dict[str, object](), "failed", "x" * 321, "call"
    )

    assert_that(get_short_error_message(report)).is_equal_to("x" * 200)


def test_reports_unknown_error_when_representation_is_missing() -> None:
    report = pytest.TestReport(
        "test.py::test_empty", ("test.py", 0, "test_empty"), dict[str, object](), "failed", None, "call"
    )

    assert_that(get_short_error_message(report)).is_equal_to("Unknown error")


def test_successful_session_sends_no_notification(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_success():\n    pass\n")

    result = pytester.runpytest_subprocess(
        "-p",
        "no:pytest_notifier",
        "-p",
        "pytest_notifier.plugin",
        "-p",
        "pytest_asyncio.plugin",
        "-o",
        "asyncio_default_fixture_loop_scope=function",
    )

    assert_that(result.stdout.str()).does_not_contain("Failed tests:")


def test_failed_session_prints_failure_notification(pytester: pytest.Pytester) -> None:
    pytester.makepyfile('def test_failure():\n    raise ValueError("specific failure")\n')

    result = pytester.runpytest_subprocess(
        "-p",
        "no:pytest_notifier",
        "-p",
        "pytest_notifier.plugin",
        "-p",
        "pytest_asyncio.plugin",
        "-o",
        "asyncio_default_fixture_loop_scope=function",
    )

    assert_that(result.stdout.str()).contains("Failed tests: 1", "specific failure")


def test_failed_setup_prints_error_notification(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        "import pytest\n@pytest.fixture()\ndef broken():\n"
        '    raise RuntimeError("setup unavailable")\ndef test_error(broken):\n    pass\n'
    )

    result = pytester.runpytest_subprocess(
        "-p",
        "no:pytest_notifier",
        "-p",
        "pytest_notifier.plugin",
        "-p",
        "pytest_asyncio.plugin",
        "-o",
        "asyncio_default_fixture_loop_scope=function",
    )

    assert_that(result.stdout.str()).contains("Errors: 1", "setup unavailable")
