UV ?= uv
CHECKMAKE ?= checkmake
# Дополнительные флаги uv sync, например --inexact для окружения, где нельзя удалять пакеты.
SYNC_ARGS ?=
PYTEST_ARGS ?=
# Дополнительные флаги pip-audit, например формат отчёта для CI.
AUDIT_ARGS ?=
# Окружение уже синхронизировано целью sync: проверки не должны менять его на ходу.
RUN := $(UV) run --no-sync

# Даже вложенный pytest не должен отправлять уведомления из .env разработчика.
export PYTEST_NOTIFIER_DESTINATIONS := 1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD := 1
export PYTHONWARNINGS := error
PYTEST_PLUGINS := -p pytest_asyncio.plugin -p pytest_httpx -p pytest_mock -p pytest_timeout \
	-p faker.contrib.pytest.plugin -p pytest_cases.plugin -p syrupy -p _hypothesis_pytestplugin \
	-p xdist.plugin -p pytest_rerunfailures -p allure_pytest.plugin -p anyio.pytest_plugin \
	-p pytest_docker

PACKAGES := $(notdir $(wildcard packages/*))
GRPC_API_PACKAGES := grpc-client grpc-client-auth
STUB_MODULES := $(notdir $(patsubst %/__init__.pyi,%,$(wildcard typings/*/__init__.pyi)))

TEST_TARGETS := $(addprefix test-,$(PACKAGES))
TYPECHECK_TARGETS := $(addprefix typecheck-,$(PACKAGES))
GEN_API_TARGETS := $(addprefix gen-test-api-,$(GRPC_API_PACKAGES))
GRPC_TEST_TARGETS := $(addprefix test-,$(GRPC_API_PACKAGES))
GRPC_TYPECHECK_TARGETS := $(addprefix typecheck-,$(GRPC_API_PACKAGES))

AUDIT_REQUIREMENTS := build/audit-requirements.txt

# Отдельное окружение на версию Python: make test PYTHON_VERSION=3.14.
ifdef PYTHON_VERSION
export UV_PYTHON := $(PYTHON_VERSION)
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/.venvs/$(PYTHON_VERSION)
endif

.DEFAULT_GOAL := help

# checkmake не читает перенос строки в .PHONY, поэтому цели объявлены у своих правил.
.PHONY: help
help: ## Показать доступные цели
	@grep -hE '^[a-z%-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-18s %s\n", $$1, $$2}'
	@echo "  test-<пакет>       Тесты одного пакета: $(PACKAGES)"
	@echo "  typecheck-<пакет>  mypy для одного пакета"

.PHONY: sync
sync: ## Установить зависимости всех пакетов строго по uv.lock
	$(UV) sync --locked --all-packages --all-extras --all-groups $(SYNC_ARGS)

.PHONY: lock
lock: ## Пересобрать uv.lock
	$(UV) lock

.PHONY: lock-check
lock-check: ## Проверить, что uv.lock соответствует pyproject.toml
	$(UV) lock --check

.PHONY: format
format: ## Отформатировать код
	$(RUN) ruff format .

.PHONY: format-check
format-check: ## Проверить форматирование без изменений
	$(RUN) ruff format --check .

.PHONY: lint
lint: ## Запустить ruff check
	$(RUN) ruff check .

.PHONY: lint-fix
lint-fix: ## Применить безопасные исправления ruff
	$(RUN) ruff check --fix .

.PHONY: typecheck
typecheck: $(TYPECHECK_TARGETS) typecheck-scripts ## Запустить mypy для всех пакетов и скриптов

# Пакеты проверяются по отдельности: у каждого свой модуль tests.
.PHONY: $(TYPECHECK_TARGETS)
$(TYPECHECK_TARGETS): typecheck-%:
	$(RUN) mypy packages/$*

.PHONY: typecheck-scripts
typecheck-scripts:
	$(RUN) mypy scripts

# Тесты gRPC-клиентов импортируют сгенерированный API.
.PHONY: $(GRPC_TYPECHECK_TARGETS)
$(GRPC_TYPECHECK_TARGETS): typecheck-%: gen-test-api-%

# Без конфига mypy проекта: warn_unused_configs ругается на overrides чужих модулей.
# Стабы описывают только используемую часть API, поэтому отсутствующие имена не ошибка.
.PHONY: stubtest
stubtest: ## Сверить стабы из typings/ с установленными библиотеками
	MYPYPATH=typings $(RUN) stubtest --ignore-missing-stub $(STUB_MODULES)

.PHONY: gen-test-api
gen-test-api: $(GEN_API_TARGETS) ## Сгенерировать тестовый gRPC API

.PHONY: $(GEN_API_TARGETS)
$(GEN_API_TARGETS): gen-test-api-%:
	rm -rf packages/$*/api
	cd packages/$* && $(RUN) bash gen-test-api.sh api

.PHONY: test
test: $(TEST_TARGETS) test-scripts test-allure-examples ## Запустить тесты всех пакетов, каждый отдельным процессом

# Отдельный процесс на пакет: одноимённые модули tests и настройки pytest не должны пересекаться.
.PHONY: $(TEST_TARGETS)
$(TEST_TARGETS): test-%:
	cd packages/$* && $(RUN) pytest $(PYTEST_PLUGINS) $(PYTEST_ARGS)

.PHONY: $(GRPC_TEST_TARGETS)
$(GRPC_TEST_TARGETS): test-%: gen-test-api-%

.PHONY: test-scripts
test-scripts: ## Запустить тесты скриптов репозитория
	$(RUN) pytest scripts $(PYTEST_PLUGINS) $(PYTEST_ARGS)

.PHONY: test-allure-examples
test-allure-examples: ## Проверить интеграционные примеры Allure с локальным httpbin
	cd packages/http-client-allure/examples && $(RUN) --project $(CURDIR) pytest $(PYTEST_PLUGINS) \
		--strict-markers --strict-config -W error $(PYTEST_ARGS)

.PHONY: build
build: ## Собрать wheel и sdist всех пакетов в dist/
	rm -rf dist
	$(UV) build --all-packages --no-sources --out-dir dist
	$(UV) run --no-project python -m scripts.skills dist

.PHONY: check-wheels
check-wheels: ## Установить каждую библиотеку из dist/ в пустое окружение и импортировать её
	$(RUN) python -m scripts.wheels dist --uv $(UV)

.PHONY: audit
audit: ## Проверить внешние зависимости из uv.lock на известные уязвимости
	mkdir -p $(dir $(AUDIT_REQUIREMENTS))
	$(UV) export --locked --all-packages --all-extras --all-groups --no-emit-workspace -o $(AUDIT_REQUIREMENTS) > /dev/null
	$(RUN) python -m pip_audit --strict --require-hashes --disable-pip -r $(AUDIT_REQUIREMENTS) $(AUDIT_ARGS)

.PHONY: lint-make
lint-make: ## Проверить Makefile линтером checkmake
	$(CHECKMAKE) --config checkmake.ini Makefile

.PHONY: check
check: format-check lint lint-make typecheck stubtest test ## Полный набор проверок

.PHONY: all
all: check ## То же, что check

.PHONY: clean
clean: ## Удалить артефакты сборки и сгенерированный API
	rm -rf dist build packages/*/api
