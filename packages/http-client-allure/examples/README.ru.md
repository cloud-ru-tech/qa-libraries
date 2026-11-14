# Демо проект для демонстрации

[English](README.md) | Русский

Тесты в этой папке гоняют настоящие HTTP-запросы к локальному [httpbin](https://github.com/mccutchen/go-httpbin)
и складывают результат в Allure. Смотреть нужно не на зеленые галочки, а на собранный отчет: каждый тест
показывает, что именно делает с ним та или иная опция.

Проект самостоятельный — он подключает `cloudru-qa-http-client-allure` как обычную зависимость, ровно
так же, как это сделает любой другой проект с автотестами. В монорепозитории зависимость берётся
из соседнего каталога, а не из PyPI.

## Что нужно

- запущенный Docker — httpbin поднимается в контейнере;
- [`uv`](https://docs.astral.sh/uv/) — ставит зависимости;
- `npx` из Node.js — только для сборки отчета.

## Запуск

Команды выполняются из каталога `packages/http-client-allure/examples`:

```shell
uv sync
uv run pytest --alluredir=allure-results
npx allure awesome allure-results --single-file
```

Отчёт появится в `allure-report/index.html`. Тесты сами поднимают httpbin и удаляют контейнер
после прогона. Чтобы оставить контейнер поднятым между прогонами, добавьте флаг `--keepalive`:

```shell
uv run pytest --alluredir=allure-results --keepalive
```

Удалить результаты прошлых прогонов: `rm -rf allure-results allure-report`.
