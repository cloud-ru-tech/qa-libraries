UV ?= uv
CHECKMAKE ?= checkmake
# Extra uv sync flags, such as --inexact when installed packages must be kept.
SYNC_ARGS ?=
PYTEST_ARGS ?=
# Extra pip-audit flags, such as the report format for CI.
AUDIT_ARGS ?=
# The sync target prepares the environment; checks must not change it as they run.
RUN := PYTHONWARNINGS=error $(UV) run --no-sync

# Prevent even nested pytest runs from sending notifications using the developer's .env.
export PYTEST_NOTIFIER_DESTINATIONS := 1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD := 1
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

# Keep a separate environment per Python version: make test PYTHON_VERSION=3.14.
ifdef PYTHON_VERSION
export UV_PYTHON := $(PYTHON_VERSION)
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/.venvs/$(PYTHON_VERSION)
endif

.DEFAULT_GOAL := help

# checkmake cannot parse line continuations in .PHONY, so declare targets next to their rules.
.PHONY: help
help: ## Show available targets
	@grep -hE '^[a-z%-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-18s %s\n", $$1, $$2}'
	@echo "  test-<package>       Test one package: $(PACKAGES)"
	@echo "  typecheck-<package>  Run mypy for one package"

.PHONY: sync
sync: ## Install dependencies for all packages from uv.lock
	$(UV) sync --locked --all-packages --all-extras --all-groups $(SYNC_ARGS)

.PHONY: lock
lock: ## Regenerate uv.lock
	$(UV) lock

.PHONY: lock-check
lock-check: ## Check that uv.lock matches pyproject.toml
	$(UV) lock --check

.PHONY: format
format: ## Format code
	$(RUN) ruff format .

.PHONY: format-check
format-check: ## Check formatting without changing files
	$(RUN) ruff format --check .

.PHONY: lint
lint: ## Run ruff check
	$(RUN) ruff check .

.PHONY: lint-fix
lint-fix: ## Apply safe Ruff fixes
	$(RUN) ruff check --fix .

.PHONY: typecheck
typecheck: $(TYPECHECK_TARGETS) typecheck-scripts ## Run mypy for all packages and scripts

# Check packages separately because each has its own tests module.
.PHONY: $(TYPECHECK_TARGETS)
$(TYPECHECK_TARGETS): typecheck-%:
	$(RUN) mypy packages/$*

.PHONY: typecheck-scripts
typecheck-scripts:
	$(RUN) mypy scripts

# gRPC client tests import the generated API.
.PHONY: $(GRPC_TYPECHECK_TARGETS)
$(GRPC_TYPECHECK_TARGETS): typecheck-%: gen-test-api-%

# Avoid the project mypy config: warn_unused_configs flags overrides for unrelated modules.
# Stubs cover only the API we use, so missing names are allowed.
.PHONY: stubtest
stubtest: ## Check typings/ stubs against installed libraries
	MYPYPATH=typings $(RUN) stubtest --ignore-missing-stub $(STUB_MODULES)

.PHONY: gen-test-api
gen-test-api: $(GEN_API_TARGETS) ## Generate the test gRPC API

.PHONY: $(GEN_API_TARGETS)
$(GEN_API_TARGETS): gen-test-api-%:
	rm -rf packages/$*/api
	cd packages/$* && $(RUN) bash gen-test-api.sh api

.PHONY: test
test: $(TEST_TARGETS) test-scripts test-allure-examples ## Test all packages, each in a separate process

# Separate processes prevent collisions between tests modules and pytest settings.
.PHONY: $(TEST_TARGETS)
$(TEST_TARGETS): test-%:
	cd packages/$* && $(RUN) pytest $(PYTEST_PLUGINS) $(PYTEST_ARGS)

.PHONY: $(GRPC_TEST_TARGETS)
$(GRPC_TEST_TARGETS): test-%: gen-test-api-%

.PHONY: test-scripts
test-scripts: ## Test repository scripts
	$(RUN) pytest scripts $(PYTEST_PLUGINS) $(PYTEST_ARGS)

.PHONY: test-allure-examples
test-allure-examples: ## Test Allure integration examples with local httpbin
	cd packages/http-client-allure/examples && $(RUN) --project $(CURDIR) pytest $(PYTEST_PLUGINS) \
		--strict-markers --strict-config -W error $(PYTEST_ARGS)

.PHONY: build
build: ## Build wheels and sdists for all packages in dist/
	rm -rf dist
	$(UV) build --all-packages --no-sources --out-dir dist
	$(UV) run --no-project python -m scripts.skills dist

.PHONY: check-wheels
check-wheels: ## Install each library from dist/ in an empty environment and import it
	$(RUN) python -m scripts.wheels dist --uv $(UV)

.PHONY: audit
audit: ## Check external dependencies from uv.lock for known vulnerabilities
	mkdir -p $(dir $(AUDIT_REQUIREMENTS))
	$(UV) export --locked --all-packages --all-extras --all-groups --no-emit-workspace -o $(AUDIT_REQUIREMENTS) > /dev/null
	$(RUN) python -m pip_audit --strict --require-hashes --disable-pip -r $(AUDIT_REQUIREMENTS) $(AUDIT_ARGS)

.PHONY: lint-make
lint-make: ## Lint Makefile with checkmake
	$(CHECKMAKE) --config checkmake.ini Makefile

.PHONY: check
check: format-check lint lint-make typecheck stubtest test ## Run all checks

.PHONY: all
all: check ## Same as check

.PHONY: clean
clean: ## Remove build artifacts and generated API
	rm -rf dist build packages/*/api
