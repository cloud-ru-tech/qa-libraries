---
paths:
  - "**/tests/**"
  - "**/conftest.py"
---

# Basic Unit Testing Rules

## 1. Don't tolerate long tests

Keep tests short and highly specific. Unit tests must be logic-free: only set up data, call the code under test, and assert the result. If setup grows beyond a few lines, extract it into fakes, fixtures, or helpers. Prefer tiny tests that fail in one clear place and immediately show what broke.

## 2. Assert only once per test

Prefer one assertion per test. Do not piggyback multiple checks into a single test, even when they share the same setup. Split each expected behavior into its own small test so failures stay precise and independent. If setup is expensive, optimize it with fixtures or caching instead of grouping assertions; use soft assertions only rarely.

Bad:

```python
# This test asserts two things at once: that the file exists and that its size is greater than zero.
def test_generates_valid_file(tmp_path: Path):
    out = tmp_path / "p.html"
    Page().save_to(out)
    assert out.exists()
    assert out.stat().st_size > 0
```

Good:

```python
def test_generates_file(tmp_path: Path):
    out = tmp_path / "p1.html"

    Page().save_to(out)

    assert out.exists()


def test_generates_non_empty_file(tmp_path: Path):
    out = tmp_path / "p2.html"

    Page().save_to(out)

    assert out.stat().st_size > 0
```

## 3. Assert at least once per test

Every test must contain at least one explicit assertion. Do not rely on the absence of exceptions as proof that behavior is correct. Assertion-free tests only increase coverage metrics without verifying anything. If failure is expected, assert it explicitly with an exception check.

## 4. Finish with an assertion

Make the assertion the last statement of the test. Do not continue the scenario after the final check, because any failure after the assertion makes the test flow confusing and harder to diagnose. A test should end with its conclusion. If you need to verify another behavior, write a separate test.

## 5. Don't assert on absence of failure

Do not treat "no exception was thrown" as a meaningful test assertion. Tests like Java assertDoesNotThrow() are usually a weak fallback when no real assertion is written. A good test should verify a concrete result: returned value, state change, or observable side effect.

Bad:

```python
def test_works_properly():
    obj = Creature()
    obj.proceed()  # test fails only when an exception occurs
```

Good:

```python
def test_works_properly():
    obj = Creature()
    result = obj.proceed()
    assert result == expected_result
```

If the side effect matters, verify it directly:

```python
def test_works_properly():
    obj = Creature()
    obj.proceed()
    assert obj.status == "done"
```

## 6. Don't fail explicitly

Do not rise exceptions with manual if checks to validate expected results in tests. That pattern is only a verbose substitute for a real assertion. When verifying output, use direct assert or assertpy `assert_that()` so the test states the expected value explicitly and clearly.

## 7. Use irregular inputs

Do not limit tests to the happy path. Keep a simple baseline test, but add separate tests with irregular, boundary, or suspicious inputs to expose hidden failures. Use strange filenames, malformed strings, suspicious paths, invalid dates, and other hostile data. Keep one test per bug type: one test for the basic contract, another for each corner case. When useful, use fuzzing or property-based testing to generate many unusual inputs automatically.

Happy path test:

```python
def test_prints_report_with_regular_filename(tmp_path: Path):
    pages = Report(tmp_path, "page.html").save()
    assert pages > 0
```

Test with irregular inputs:

```python
def test_rejects_invalid_filename(tmp_path: Path):
    with pytest.raises(ValueError):
        Report(tmp_path, "\x00\x00bad.html").save()
```

## 8. Be creative with inputs

Do not reuse the same literal inputs across unrelated tests unless the shared value is itself important to the behavior being tested. Repeating the same string, number, or object in multiple tests can create a false impression that the tests are logically connected or that the value has special meaning. Each test should use its own data, chosen specifically for its purpose. Random data generators like Faker can help diversify inputs when appropriate.

## 9. Write descriptive failure messages

Do not leave assertions unexplained, especially when they rely on non-obvious values such as magic numbers. Add a clear failure message so that when the test breaks, the reason is immediately visible. Good failure messages make large test suites more useful: even many failing tests can help locate the bug quickly if each failure clearly explains what went wrong.

Bad:

```python
def test_generates_logo(tmp_path: Path):
    png = tmp_path / "logo.png"
    Logo("IBM").save_to(png)
    assert png.stat().st_size >= 67
```

Good:

```python
MIN_PNG_SIZE = 67


def test_generates_logo(tmp_path: Path):
    png = tmp_path / "logo.png"
    Logo("IBM").save_to(png)
    assert png.stat().st_size >= MIN_PNG_SIZE, "The file is too small to be a valid PNG image"
```

## 10. Don't share anything

Tests should be fully isolated and idempotent. A test is good when it gives the same result whether it runs alone, inside a suite, or in any execution order. Sharing directories, files, database records, object attributes, or other fixtures between tests breaks isolation and often causes flaky behavior or race conditions. Prefer fixtures that are local to each test. If every test owns its own resources, `setUp()` and `tearDown()` often become unnecessary, and a bit of duplication is acceptable.

Bad:

```python
class TestPage:
    shared_dir = Path(tempfile.mkdtemp())

    def test_saves_page(self):
        path = self.shared_dir / "page.html"
        Page(path).save()
        assert path.exists()

    def test_counts_pages(self):
        path = self.shared_dir / "page.html"
        total = Page(path).count()
        assert total >= 0
```

Good:

```python
def test_saves_page(tmp_path: Path):
    path = tmp_path / "page.html"
    Page(path).save()
    assert path.exists()


def test_counts_pages(tmp_path: Path):
    path = tmp_path / "page.html"
    Page(path).save()
    total = Page(path).count()
    assert total >= 1
```

## 11. Don't use static literals

Do not eliminate duplicate literals in tests by extracting them into a shared constant. A shared test constant makes unrelated tests depend on the same input and creates an artificial connection between them. In tests, input diversity is more important than stylistic deduplication. Prefer different literals in different tests unless the shared value is itself part of the behavior being verified.

Bad:

```python
TEXT = "Hello!"


def test_rotates_twice():
    assert rotate(rotate(TEXT)) == TEXT


def test_puts_last_letter_first():
    assert rotate(TEXT)[0] == TEXT[-1]
```

Good:

```python
def test_rotates_twice():
    text = "planet"
    assert rotate(rotate(text)) == text


def test_puts_last_letter_first():
    assert rotate("mouse?")[0] == "?"
```

If a shared value really matters to the tests intent, a constant is acceptable:

```python
EMPTY_TEXT = ""


def test_rotating_empty_string_returns_empty_string():
    assert rotate(EMPTY_TEXT) == EMPTY_TEXT
```

## 12. Label constants as variables

Avoid assertions that compare results to unexplained literals. Even if the test is correct, a hardcoded value may make the intent unclear. When the expected value comes from the test setup, bind it to a well-named local variable and reuse it in both the input and the assertion. This makes the relationship explicit and improves readability by showing that the role of the value matters more than the value itself.

Bad:

```python
def test_finds_prime_number():
    nums = [4, 19, 32, 67, 664, 21]
    n = prime(nums)
    assert n == 19
```

Good:

```python
def test_finds_prime_number():
    expected_prime = 19
    nums = [4, expected_prime, 32, 67, 664, 21]
    n = prime(nums)
    assert n == expected_prime
```

## 13. Respect object borders

Do not test private methods by breaking encapsulation with reflection or similar hacks. A private method is hidden so the class can change or remove it without affecting users. Good tests should interact only with the public behavior available to real users. If important logic is hard to test without reaching into internals, treat that as a design signal: the class may need to be refactored into smaller, testable units rather than exposing or probing hidden implementation details.

## 14. Spell out test names

Test names should describe the behavior of the object under test as a complete English phrase, implicitly starting with it. Prefer names like buildsEmptyPngImage over canBuildEmptyPngImage or shouldBuildEmptyPngImage, since extra prefixes add noise without adding meaning. The name should describe what the tested object does, not what the test script does. For example, checksThatAnEmptyImageIsBuilt is weaker because it describes the test procedure rather than the expected behavior of the object.

## 15. Make no comments

Do not place comments inside tests or above them to explain behavior, steps, or old code. Commented-out lines, procedural explanations, and test-level documentation usually signal that the test is unclear and needs to be rewritten, not annotated. Tests should tell their story through good naming, focused structure, and readable code. If a test needs comments to be understood, improve the test itself instead of documenting it.

Bad:

```python
def test_translates():
    translator = InChinese("taxi")
    # translator.set_style("simplified")
    assert translator.text() == "出租车"
```

Bad:

```python
def test_translates():
    # Creating a translator
    translator = InChinese("taxi")
    # Switching to simplified charset
    translator.set_style("simplified")
    # Checking the output
    assert translator.text() == "出租车"
```

Bad:

```python
# The engine calculates car speed using visible indicators.
def test_works_properly():
    engine = Engine()
    result = engine.eval()
    assert result == 42
```

Good:

```python
def test_calculates_speed_from_visible_indicators():
    engine = Engine()
    result = engine.eval()
    assert result == 42
```

## 16. Be reasonable with demands

Test only the behavior that the object explicitly promises through its contract, documentation, or public API. If a method guarantees that it throws an exception, but says nothing about the exact exception message, then asserting the message text is too strict and couples the test to an implementation detail. Do not assume undocumented behavior. If some behavior matters and should remain stable, it must first be documented as part of the contract, and only then should tests depend on it.

Bad:

```python
def test_fails_when_bad_file_extension(tmp_path: Path):
    with pytest.raises(BadExtensionError) as error:
        Page().save_to(tmp_path / "a.pdf")

    assert "File name must end with .html" in str(error.value)
```

Prefer this when the contract only guarantees the error type:

```python
def test_fails_when_bad_file_extension(tmp_path: Path):
    with pytest.raises(BadExtensionError):
        Page().save_to(tmp_path / "a.pdf")
```

When the error text is contractually specified, document that explicitly before asserting on it:

```python
def test_reports_documented_error_message_for_bad_extension(tmp_path: Path):
    with pytest.raises(BadExtensionError) as error:
        Page().save_to(tmp_path / "a.pdf")

    assert str(error.value) == "File name must end with .html"
```

## 17. Assert where it hurts most

Prefer assertions that verify the actual meaning of the result, not just the fact that some operation completed. A weak test only confirms that "something happened" such as an object being created, a file appearing, or a call returning without error. A strong test checks the behavior that actually matters: returned data, structure, state changes, side effects, or contractually relevant content. The more specific the assertion, the more useful the test is at catching real regressions.

Weak variant:

```python
def test_creates_user():
    user = create_user("alice")
    assert user is not None
```

Better:

```python
def test_creates_user_with_expected_data():
    user = create_user("alice")
    assert user is not None
    assert user.name == "alice"
    assert user.is_active is True
```

## 18. Avoid overtesting

Do not rush to write tests for trivial classes that contain almost no logic and are unlikely to fail on their own. If a class is just a small mutable data holder or a thin wrapper, direct tests for it often add little value. Instead, test the higher-level classes that use it. If this tiny class later becomes a real source of bugs, then add focused tests. Very small code that seems unworthy of testing is often a good candidate for refactoring or removal.

Primitive class:

```python
class Cite:
    def __init__(self):
        self.author = None
        self.year = None

    def cite(self):
        return f"{self.author} ({self.year})"
```

## 19. Don't test private entries

Do not make private methods public just to test them. Tests must adapt to the object’s intended interface, not force the interface to expand for testing convenience. If important logic inside a private method needs direct verification, extract that logic into a new class and test it there. Otherwise, reproduce and verify the bug through the existing public methods. If a method is public only because tests need access to it, that is a design smell and the method should usually be made private again.

## 20. Close resources

Tests must clean up every system resource they open, such as files, sockets, processes, or temporary handles. Leaving resources unclosed can introduce flakiness and make the suite less reliable. Resource cleanup should be guaranteed even when the test fails, so the assertion remains the last meaningful step of the scenario. Use fixtures or language mechanisms that ensure automatic cleanup.

Bad:

```python
def test_counts_lines():
    file_obj = open("fixtures/foo.txt", "r", encoding="utf-8")
    assert Lines(file_obj).total() == 42
```

Good:

```python
def test_counts_lines():
    with open("fixtures/foo.txt", "r", encoding="utf-8") as file_obj:
        assert Lines(file_obj).total() == 42
```

If the resource is more involved and needs its own setup, you can move cleanup into a fixture:

```python
@pytest.fixture
def lines_file():
    with open("fixtures/foo.txt", "r", encoding="utf-8") as file_obj:
        yield file_obj


def test_counts_lines(lines_file: TextIO):
    assert Lines(lines_file).total() == 42
```

## 21. Don't play along

Do not add production methods solely to make tests easier. When code exists only for tests and is not needed by real feature behavior, it pollutes the design and weakens the object’s interface. Tests must adapt to the existing public behavior of the object, even if that means repeating some verification logic inside the tests. If testing is awkward without adding helper methods to production code, treat that as a design signal rather than a reason to expand the API.

## 22. Fail gradually, in many steps

Do not rely on a single highly specific test to cover an entire feature. A better approach is to create several focused tests for the same behavior, with assertions that progress from generic to specific. This gives clearer diagnostics: if the feature breaks, earlier tests reveal whether the failure is in execution, artifact creation, structural validity, or final content. Multiple layered tests make failures easier to localize than one deep test alone.

Weak variant:

```python
def test_generates_logo_as_png(tmp_path: Path):
    file_path = tmp_path / "test.png"
    Logo("IBM").save(file_path)

    with Image.open(file_path) as img:
        assert img.format == "PNG"
```

Strong variant:

```python
MIN_PNG_SIZE = 67


def test_generates_logo_file(tmp_path: Path):
    file_path = tmp_path / "test.png"

    Logo("IBM").save(file_path)

    assert file_path.exists()


def test_generates_non_empty_logo_file(tmp_path: Path):
    file_path = tmp_path / "test.png"

    Logo("IBM").save(file_path)

    assert file_path.stat().st_size > MIN_PNG_SIZE, "The file is too small to be a valid PNG image"


def test_generates_logo_as_png(tmp_path: Path):
    file_path = tmp_path / "test.png"
    Logo("IBM").save(file_path)

    with Image.open(file_path) as img:
        assert img.format == "PNG"
```

## 23. Don't assert on side-effects

Assert only on the behavior promised by the contract, not on incidental side effects such as logging. This rule applies to any test; the PDF report below is only a concrete example. Side effects are implementation details, so tests that rely on them become fragile and may fail even when the feature still works correctly. If a feature is supposed to create a file, return data, or change state, verify that promised outcome directly. In the PDF example, inspect the generated file and verify its meaningful result, such as the page count. Logging should be tested only when it is explicitly part of the feature contract.

Bad example with a PDF report:

```python
def test_creates_pdf_report(tmp_path: Path):
    file_path = tmp_path / "foo.pdf"

    Report(file_path).save()

    assert "Created 14 pages" in Logs.recent()
```

Good example with a PDF report:

```python
from pypdf import PdfReader


def test_creates_pdf_report(tmp_path: Path):
    file_path = tmp_path / "foo.pdf"

    Report(file_path).save()

    reader = PdfReader(file_path)
    assert len(reader.pages) == 14
```

## 24. Be creative with asserts

Do not stop at the first obvious assertion. This principle applies to any test; the PDF document below is only a concrete example. After exercising a feature, inspect the result from multiple useful angles and turn each meaningful property into its own focused test. In general, you should check whichever properties best describe the real outcome of the feature. For example, a generated PDF can be checked for existence, non-empty size, correct extension, valid format, expected page count, or expected text content. The more precisely your assertions describe the real outcome, the more defects your tests can expose.

Weak variant using a PDF example:

```python
def test_generates_pdf_document(tmp_path: Path):
    file_path = Page("Hello, world!").save_to_file(tmp_path)

    assert file_path.exists()
```

Stronger variants using the same PDF example:

```python
from pypdf import PdfReader


def test_generates_non_empty_pdf_document(tmp_path: Path):
    file_path = Page("Hello, world!").save_to_file(tmp_path)

    assert file_path.stat().st_size > 0


def test_generates_pdf_file_with_expected_extension(tmp_path: Path):
    file_path = Page("Hello, world!").save_to_file(tmp_path)

    assert file_path.suffix == ".pdf"


def test_generates_regular_pdf_file(tmp_path: Path):
    file_path = Page("Hello, world!").save_to_file(tmp_path)

    assert file_path.is_file()


def test_generates_valid_pdf_document(tmp_path: Path):
    file_path = Page("Hello, world!").save_to_file(tmp_path)

    reader = PdfReader(file_path)
    assert len(reader.pages) >= 1


def test_generates_pdf_with_expected_text(tmp_path: Path):
    file_path = Page("Hello, world!").save_to_file(tmp_path)

    reader = PdfReader(file_path)
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Hello, world!" in text
```

## 25. Don't test getters, setters, or ctors

Do not spend tests on trivial getters, setters, or constructors, because such tests usually verify wiring instead of behavior. A better design reduces the need for them in the first place: avoid getters and setters when possible, prefer immutable objects, and keep constructors free of business logic. Then tests can focus on real behavior and contracts instead of checking that fields were merely assigned or returned.

## 26. Clean up

Tests must not trust the environment they start in. This principle applies to any external state; the shared database below is only a concrete example. Each test should establish the clean, expected state it needs for itself so that it remains idempotent. Clean up only the resources your own test depends on, and do not rely on leftovers from previous runs. Avoid broad shared cleanup when it makes tests slow or breaks parallel execution; the best design gives each test isolated resources, such as its own database.

Bad example with shared database state:

```python
from typing import Protocol


class SqlExecutor(Protocol):
    def exec(self, query: str) -> None: ...


def test_increments_balance_by_one_payment(pgsql: SqlExecutor) -> None:
    customer = Customer(42)

    pgsql.exec("SELECT add_payment(42, 19.99)")

    assert customer.balance() == 19.99
```

Better example with explicit cleanup:

```python
from typing import Protocol


class SqlExecutor(Protocol):
    def exec(self, query: str) -> None: ...


def test_increments_balance_by_one_payment(pgsql: SqlExecutor) -> None:
    pgsql.exec("TRUNCATE payment CASCADE")
    customer = Customer(42)

    pgsql.exec("SELECT add_payment(42, 19.99)")

    assert customer.balance() == 19.99
```

## 27. Don't mock

Prefer fakes over mocks. This principle applies to any dependency; the database below is only a concrete example. Mocks often make tests harder to understand and tightly couple them to the current interaction details of the implementation. Fakes are simpler substitutes designed to behave like the real dependency in a reduced but coherent way, so tests can verify outcomes instead of internal call patterns. Use mocks only in rare cases when no reasonable fake can exist.

Bad example with a mock database:

```python
from typing import Protocol
from unittest.mock import Mock


class Database(Protocol):
    def query(self, sql: str) -> int: ...


def test_saves_to_database() -> None:
    db: Mock = Mock(spec=Database)
    db.query.return_value = 42

    Page().save_to(db)

    db.query.assert_called_with("INSERT INTO page ...")
```

Better example with a fake database:

```python
from typing import Protocol


class Database(Protocol):
    def save_page(self, page: "Page") -> None: ...

    def pages_count(self) -> int: ...


class FakeDatabase:
    def __init__(self) -> None:
        self._pages_count = 0

    def save_page(self, page: "Page") -> None:
        self._pages_count += 1

    def pages_count(self) -> int:
        return self._pages_count


def test_saves_to_database() -> None:
    db = FakeDatabase()

    Page().save_to(db)

    assert db.pages_count() == 1
```

## 28. Don't forgive, disable instead

Do not weaken a test just to accommodate a known bug. This principle applies to any incomplete feature; the prime-number function below is only a concrete example. A forgiving test encodes incorrect behavior as if it were acceptable and may later fail for the wrong reason when the bug is fixed. Instead, write the correct assertion and temporarily disable the test with a clear TODO or FIXME note that explains the known issue and what should happen once it is resolved.

Example feature code with a known limitation:

```python
def primes(n: int) -> list[int]:
    return [2, 3, 5, 7, 11][:n]
```

Bad example that forgives the bug:

```python
def test_finds_as_many_as_it_can() -> None:
    assert len(primes(42)) == 5
```

Better example with a disabled test:

```python
import pytest


@pytest.mark.skip(
    reason="TODO #657: primes() currently returns only the first five items; enable this test after the bug is fixed."
)
def test_finds_requested_number_of_items() -> None:
    assert len(primes(42)) == 42
```

## 29. Aim for one-statement tests

Aim to make each test read as a single declarative assertion. This principle applies to any kind of test; the HTML and assertion examples below are only concrete illustrations. When setup or verification becomes noisy, move that detail into fixtures, fakes, helpers, or custom assertions so the test body states only the intent. One-statement tests are usually shorter, easier to reuse, and easier to read because the expected behavior is visible immediately.

Simple example with HTML output:

```python
def test_generates_html_content() -> None:
    assert "<html>" in Page("Hello, world!").html()
```

More expressive example with assertpy:

```python
from assertpy import assert_that


def test_generates_proper_html_content() -> None:
    assert_that(Page("Hey, dude!").html()).contains("<html>", "</html>")
```

One-statement test with a custom assertion:

```python
from pathlib import Path
from typing import Any

from assertpy import add_extension, assert_that


def saved_to_dir(self: Any, directory: Path) -> Any:
    self.val.save_to(directory)
    assert_that((directory / "index.html").exists()).is_true()
    return self


add_extension(saved_to_dir)


def test_builds_and_saves(tmp_path: Path) -> None:
    assert_that(Page("How do you do!")).saved_to_dir(tmp_path)
```

## 30. Use assertpy in Python and Hamcrest in other languages

Use expressive assertions consistently across the test suite, but standardize them by language. In Python projects, use `assertpy`. In projects written in other languages, use `Hamcrest` where it is available. These libraries can make tests and failure messages easier to read, but mixing several assertion styles inside the same project reduces clarity and consistency.

## 31. Even bad tests are welcome

No test is often worse than a weak test, because even a clumsy automated check can execute real code, catch obvious failures, and verify that the application still starts. Temporary and awkward tests are acceptable if they provide some signal and are clearly marked as provisional. However, this tolerance has limits: tests built mostly on mocks, brittle expectations, forgiveness, or flakiness create false confidence and should be disabled or replaced.

## 32. Be a good boy scout

Whenever you touch the codebase, try to leave the automated tests in a slightly better state than before. Even if you are not fixing a bug or building a major feature, add at least one useful test alongside the change. Small, steady improvements in test coverage make the system safer to evolve over time.
