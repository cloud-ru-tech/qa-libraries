from dataclasses import dataclass, field


@dataclass
class TestFailureInfo:
    """Информация об упавшем тесте или ошибке."""

    nodeid: str
    name: str
    file_path: str
    error_message: str
    traceback: str | None
    duration: float


@dataclass
class TestResults:
    """Результаты прогона тестов."""

    collected: int
    passed: int
    failed: int
    error: int
    skipped: int
    xfailed: int
    xpassed: int
    exitstatus: int
    exitstatus_text: str
    failures: list[TestFailureInfo] = field(default_factory=list)
    errors: list[TestFailureInfo] = field(default_factory=list)
