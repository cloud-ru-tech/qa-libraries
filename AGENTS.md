# Agent instructions

## Language

- Write all code comments and docstrings in English.

## Python environment and dependencies

- Use Python 3.13-compatible syntax and APIs. Preserve compatibility with the Python versions tested in CI.
- Use the existing uv workspace and shared `uv.lock`. Run development commands from the repository root.
- Install dependencies in a virtual environment, never in system Python. Ask before adding a dependency.
- Follow the existing package layout: library modules under `packages/<library>/`, with tests in a separate `tests/`
  directory. Use the existing Hatchling build configuration.

## Python code

- Keep functions short and focused on one responsibility. Limit nested `for` and `if` blocks to three levels.
- Instantiate classes directly instead of adding functions that only forward arguments to a constructor.
- Name actions with verbs and prefix private functions and methods with an underscore.
- Annotate every function parameter and return value, including `-> None`. Use precise types and parameterized
  collections; avoid `Any` and bare container types to satisfy strict mypy checks.
- Keep imports at the top of the module, followed by constants and globals, public functions, and private helpers.
- In classes, place class attributes first, then the initializer, public methods, and private methods.
- Add `try`/`except` only when the code needs to handle an error. Do not nest `try`/`except` blocks.
- When a signature or argument list needs multiple lines, put each argument on its own line and include a trailing comma.
- Put reusable Python scripts in `.py` files instead of multiline shell heredocs.

## Docstrings and comments

- Document public production classes, functions, and methods with reStructuredText docstrings.
- Start function docstrings with an imperative sentence ending in a period. Use `:param:`, `:returns:`, and `:raises:`
  fields to describe the contract; leave types in annotations rather than `:type:` or `:rtype:` fields.
- Use double backticks for inline code in docstrings and raw docstrings when they contain backslashes.
- Keep comments minimal and explain non-obvious reasons. Express the code's behavior through names and structure.
- Place explanations of variables and type aliases in comments above the declaration, never in standalone string literals.

## Logging

- Use the package's logger for diagnostics instead of `print`. Keep CLI results separate from diagnostic logging.
- Never log passwords, tokens, or personal data. Do not use emoji in comments or log messages.

## Testing rules

When writing or reviewing unit or integration tests, read and follow the
[testing rules](.agents/rules/unit-tests/README.md), including its linked documents.

## Validation

- After Python changes, run formatting, lint, type checks, and tests using the existing Makefile targets. For a library,
  use `make format lint`, `make typecheck-<package>`, and `make test-<package>`; for repository scripts, use
  `make typecheck-scripts test-scripts`. Use `make check` for the full suite.
- Fix the cause of a diagnostic. Ask before adding `# noqa` or `# type: ignore` suppressions.

## Commits

- Follow Conventional Commits 1.0.0: `<type>[optional scope]: <description>`. Mark breaking changes with `!` or a
  `BREAKING CHANGE:` footer.
