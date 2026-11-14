# Contributing

English | [Русский](CONTRIBUTING.ru.md)

Thank you for helping the project. This document describes the rules for accepting changes.
By participating, you agree to follow the [code of conduct](CODE_OF_CONDUCT.md).

## Before you start

- Found a bug, a documentation error, or a missing option? Open an [issue](#issue).
- Discuss a new library or a breaking API change in an issue first, so you do not need
to rework a finished pull request.
- Submit typos, documentation fixes, and clear bug fixes directly as pull requests.

## Issue

Use the format `type(library): title` for issue titles:

```text
bug(http-client-retries): Retry-After header is ignored
feature(grpc-client): keepalive option
docs(explicit-wait): timeout missing from the example
```

Use one of these three types:

- `bug` — the library does not work as documented;
- `feature` — a new option or feature;
- `docs` — an error or gap in a README or skill.

Use the library's directory name from `packages/`. If the issue is not about one library —
a new library, CI, or the whole repository — omit the parentheses: `feature: Kafka library`.

Make the issue title describe the main problem or requested feature.

## Environment

You need [`uv`](https://docs.astral.sh/uv/), GNU Make, and [`checkmake`](https://github.com/checkmake/checkmake). Tests for the gRPC and SSH clients also require Docker. Run all commands from the repository root:

```shell
make sync              # install dependencies for all libraries from uv.lock
make check             # formatting, linters, mypy, and tests for the entire workspace
make test-http-client  # tests for one library
make help              # all available targets
```

CI checks the code on Python 3.13 and 3.14. To check the second version locally, run:
`make sync test PYTHON_VERSION=3.14`.

## Code requirements

- Checks are strict: ruff with all rules, mypy in strict mode, and warnings treated as
errors. Linters and static analyzers must pass without errors.
- Use `noqa`, `type: ignore`, or weaker check settings only with an explanation in the pull request.
- Discuss new dependencies in the pull request. Set version bounds: `httpx>=0.28.1,<0.29`.
- Cover new behavior and fixed bugs with tests in `packages/<name>/tests`.
- Write docstrings in reST format: `:param:`, `:returns:`, `:raises:`.
- When the API changes, update the library README and its skill in `.agents/skills/<name>-usage`.
- Implement client extensions as `ClientOption` options rather than client subclasses.
The [README](README.md#idea) explains how options work.

## Commits

Write commit messages using [Conventional Commits](https://www.conventionalcommits.org/ru/v1.0.0/),
with the library name in parentheses:

```text
feat(http-client-retries): respect the Retry-After header
fix(grpc-client-auth): refresh the token before it expires
docs(explicit-wait): example of waiting with a timeout
```

Mark breaking changes with `!` after the type and a `BREAKING CHANGE:` line in the commit body.
For changes outside libraries, omit the package name: `ci: ...`, `build: ...`, `docs: ...`.

## Versions

Versions follow [SemVer](https://semver.org/lang/ru/). The pull request author bumps the version
in `packages/<name>/pyproject.toml`:

- patch — a fix without an API change;
- minor — a new feature that keeps existing code working;
- major — a breaking API change.

The version must contain exactly three numbers, for example `1.4.2`: the release rejects other formats.
When bumping the major version, update the upper version bounds in dependent libraries.
Changes outside the published package (CI and root files) do not change its version.

## Pull request

- Open the pull request against `master`.
- Explain what changed and why in the description.
- Merge the pull request after CI passes and a maintainer approves it.

## New library

1. Create `packages/<name>` using a neighboring library as an example. The PyPI package is named
 `cloudru-qa-<name>`, and the module uses `<name>` with underscores.
2. Add the package to `[tool.uv.sources]` in the root `pyproject.toml` and run `make lock`.
3. Add `LICENSE` and `README.md` to the library directory, as in neighboring libraries.
4. Describe the API in the `.agents/skills/<name>-usage` skill and link it with a symbolic link
 from `packages/<name>/.agents/skills`.
5. Add the library to the list in the root [README](README.md#libraries).

Before the first release, maintainers configure the package on PyPI.

## Releases

Maintainers publish releases by adding a `<name>/v<version>` tag to a commit on `master`, for example
`http-client/v1.0.0`. CI checks the tag against the version in `pyproject.toml`, runs the checks again,
and publishes the package to PyPI.

## License

By submitting a pull request, you agree that your contribution is distributed
under the [Apache-2.0](LICENSE) license.
