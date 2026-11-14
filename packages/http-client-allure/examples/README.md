# Demo project

English | [Русский](README.ru.md)

Tests in this directory send real HTTP requests to a local [httpbin](https://github.com/mccutchen/go-httpbin)
and save the results in Allure. Inspect the generated report: each test
shows exactly how an option affects it, beyond simply passing.

This is a standalone project: it uses `cloudru-qa-http-client-allure` as a regular dependency,
just like any automated test project. In the monorepo, the dependency comes
from the neighboring directory rather than PyPI.

## Requirements

- Docker running — httpbin starts in a container;
- [`uv`](https://docs.astral.sh/uv/) — installs dependencies;
- Node.js `npx` — only for building the report.

## Running

Run commands from `packages/http-client-allure/examples`:

```shell
uv sync
uv run pytest --alluredir=allure-results
npx allure awesome allure-results --single-file
```

The report is written to `allure-report/index.html`. Tests start httpbin and remove its container
after the run. To keep the container between runs, add `--keepalive`:

```shell
uv run pytest --alluredir=allure-results --keepalive
```

Remove results from previous runs: `rm -rf allure-results allure-report`.
