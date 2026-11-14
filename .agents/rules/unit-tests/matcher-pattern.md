---
paths:
  - "**/tests/**"
  - "**/conftest.py"
---

# Matcher Pattern

The matcher pattern keeps verification logic out of the test body.

Tests should describe **what** behavior is expected, not **how** to inspect the result. If a check needs loops, branching, parsing, normalization, regex work, or multi-step comparisons, move that logic into a matcher or assertion object with a clear domain name.

### Core rule

Do not place assertion logic with control flow inside tests.

The test body should stay close to:

1. arrange input
2. act
3. assert with a matcher

If the assertion needs internal logic, the matcher is the right place for it.

### Why this pattern exists

Custom matchers are useful because they:

- keep tests short and intention-revealing
- make repeated checks reusable
- produce better failure messages than ad-hoc `if` blocks
- let the test speak in domain terms instead of parser details
- keep parsing and comparison code close to the assertion that needs it

This follows the same idea used by Hamcrest custom matchers: the matcher owns the matching logic and the failure description, while the test only states the expectation.

### When to use it

Use the matcher pattern when a check involves any of the following:

- loops over rows, elements, or fields
- conditional logic
- parsing HTML, JSON, XML, logs, SQL output, CLI output, or files
- normalization such as trimming, sorting, rounding, or lowercasing
- checking several fields that together form one business rule
- repeated assertion logic across multiple tests
- domain-specific expectations that deserve a business name

### When not to use it

Do not create a matcher for trivial checks such as:

- plain equality
- a single boolean flag
- a simple length or emptiness check
- one-off assertions that are already obvious inline

Do not use matchers to hide setup, side effects, or multiple unrelated expectations inside one vague helper.

## Design rules

- Give matchers names that read like requirements.
- Pass expected values into the matcher; pass the actual value only at assertion time.
- Keep matchers stateless, or store only expected parameters.
- Put loops, branches, parsing, and normalization inside the matcher, not in the test.
- Make failure messages explain both the expectation and the mismatch.
- Prefer one public matcher per business concept.
- Keep matchers in test-support modules or helper packages rather than in production code unless the matcher is part of a shared runtime contract.
- Keep tests explicit: the matcher should hide comparison mechanics, not the meaning of the check.

## Bad vs Good

Bad:

```python
def test_renders_summary_table():
    report = build_report()
    rows = parse_html(report.html)

    assert len(rows) == 3
    assert rows[0]["status"].strip().lower() == "done"
    assert rows[1]["status"].strip().lower() == "done"
    assert rows[2]["status"].strip().lower() == "failed"
```

Good:

```python
from testsupport.assertions import assert_that


def test_renders_summary_table():
    report = build_report()

    assert_that(report).has_summary_statuses(["done", "done", "failed"])
```

The good variant still verifies the same behavior, but the parsing, normalization, and iteration are moved into a named matcher.

## Python with assertpy

`assertpy` documents custom assertions via `add_extension()`. But for project code prefer a dedicated subclass of `AssertionBuilder` exposed through your own local `assert_that(...)` function. Import that function in tests instead of importing `assert_that` from `assertpy`. This gives better IDE help, better type-checker behavior, and keeps custom assertions local to the test suite.

### Recommended Shape

```python
from typing import Any, Self

from assertpy import AssertionBuilder


class ResponseAssertions(AssertionBuilder):
    def has_status(self, expected: int) -> Self:
        actual_status = self.val.status_code
        if actual_status != expected:
            self.error(f"Expected status <{expected}>, but was <{actual_status}>")
        return self

    def has_json_field(self, name: str, expected: Any) -> Self:
        actual_body = self._json_body()
        actual_value = actual_body.get(name)
        if actual_value != expected:
            self.error(f"Expected JSON field <{name}> to be <{expected}>, but was <{actual_value}> in <{actual_body}>")
        return self

    def _json_body(self) -> dict[str, Any]:
        return self.val.json()


def assert_that(actual: Any) -> ResponseAssertions:
    return ResponseAssertions(actual)


def test_creates_user():
    response = client.post("/users", json={"email": "sam@example.com"})

    assert_that(response).has_status(201)


def test_returns_created_email():
    response = client.post("/users", json={"email": "sam@example.com"})

    assert_that(response).has_json_field("email", "sam@example.com")
```

### Python Rules

- Do not parse JSON, HTML, logs, or exception text inside the test body if the same parsing can live in a matcher.
- Use `self.val` as the actual value under test.
- Use `self.error(...)` to produce the assertion failure.
- Keep private helper methods inside the matcher class when they support one matcher family.
- Prefer a locally defined `assert_that(...)` function over globally registering extensions when type safety matters.
- Import your project-local `assert_that` in tests instead of `assertpy.assert_that`.

## Hamcrest-Style Matchers

Hamcrest custom matchers are a strong reference design for this pattern.

The key idea is simple:

- one object holds the expected values
- one method performs the match
- one method describes the expectation
- one method describes the mismatch

This is what makes matcher-based assertions readable and debuggable.

In Java Hamcrest, that usually appears as methods such as `matchesSafely(...)` and `describeTo(...)`. PyHamcrest follows the same idea with `_matches(...)` and `describe_to(...)`. The exact API can change by language, but the design should stay the same.

## Practical Guidance

- Keep one matcher invocation per test when practical.
- If a matcher starts checking unrelated concerns, split it.
- If a matcher name sounds procedural, rename it in business terms.
- If a matcher is reused across many files, move it to shared test support.
- If a matcher is used only once and the check is trivial, inline it instead.

## Summary

Matcher pattern means:

- tests express intent
- matchers contain verification mechanics
- failure messages stay rich
- repeated assertion logic becomes reusable

When a test starts looking like a parser or a mini algorithm, stop and extract a matcher.
