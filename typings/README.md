# typings

English | [Русский](README.ru.md)

Type stubs for third-party libraries without suitable annotations:

- `glom` — provides neither `py.typed` nor stubs;
- `allure_commons` — includes `py.typed`, but public functions (`allure.title`, `allure.step`, `allure.attach`) have no annotations.

Without stubs, strict mypy (`disallow_any_expr`, `disallow_any_decorated`) reports errors on every
call to these libraries. Do not disable checks with `ignore_missing_imports`: this weakens checking for the entire module, not only the library calls.

The stubs describe only the API used by packages in this repository. The directory is included
through `mypy_path` in the root `pyproject.toml` and is not included in built packages.

When updating `glom` or `allure-pytest`, check the stubs against the installed versions:

```shell
make stubtest
```

Add a new library here only if mypy cannot access its types and there is no suitable `types-*` package on PyPI.

Do not add `google.rpc` here: `googleapis-common-protos` provides its own `.pyi` files, but without
a `py.typed` marker. mypy reads them through `follow_untyped_imports` in the root `pyproject.toml`.
This is an agreed decision; no custom stub for `google.rpc` is needed.
