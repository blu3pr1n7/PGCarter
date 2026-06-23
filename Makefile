.PHONY: help install dev lint format typecheck test test-unit test-integration \
        test-all coverage clean run analyze db-up db-down db-logs db-psql e2e \
        e2e-analyze

PYTHON ?= .venv/bin/python
UV ?= uv
COMPOSE ?= docker compose

# Connection details for the dockerised test database (see docker-compose.yml).
export SQLDUMP_TEST_HOST ?= localhost
export SQLDUMP_TEST_PORT ?= 55432
export SQLDUMP_TEST_DB   ?= sqldump_test
export SQLDUMP_TEST_USER ?= sqldump
export SQLDUMP_TEST_PASSWORD ?= sqldump

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	$(UV) pip install -e .

dev:  ## Install the package with dev dependencies
	$(UV) pip install -e ".[dev]"

lint:  ## Run ruff lint checks
	$(PYTHON) -m ruff check sql_dump tests

format:  ## Auto-format with ruff
	$(PYTHON) -m ruff format sql_dump tests
	$(PYTHON) -m ruff check --fix sql_dump tests

typecheck:  ## Run mypy
	$(PYTHON) -m mypy sql_dump

test: test-unit  ## Run the unit test suite (alias)

test-unit:  ## Run unit tests (no database required)
	$(PYTHON) -m pytest -m "not integration"

test-integration: db-up  ## Start the test DB and run integration tests
	$(PYTHON) -m pytest -m integration

test-all: db-up  ## Run the full suite (unit + integration) against the test DB
	$(PYTHON) -m pytest

coverage:  ## Run tests with coverage report
	$(PYTHON) -m pytest -m "not integration" --cov=sql_dump --cov-report=term-missing

run:  ## Run sql-dump index (pass ARGS="--database mydb ...")
	$(PYTHON) -m sql_dump.cli index $(ARGS)

analyze:  ## Run sql-dump analyze (pass ARGS="--input ./json ..." or "--database ...")
	$(PYTHON) -m sql_dump.cli analyze $(ARGS)

# --- Dockerised test database ----------------------------------------------

db-up:  ## Start the test PostgreSQL and wait until healthy
	$(COMPOSE) up -d --wait

db-down:  ## Stop and remove the test PostgreSQL (and its data)
	$(COMPOSE) down -v

db-logs:  ## Tail the test database logs
	$(COMPOSE) logs -f postgres

db-psql:  ## Open a psql shell in the test database
	$(COMPOSE) exec postgres psql -U $(SQLDUMP_TEST_USER) -d $(SQLDUMP_TEST_DB)

e2e: db-up  ## Run the index CLI end-to-end against the test DB into ./build/e2e
	rm -rf build/e2e
	$(PYTHON) -m sql_dump.cli index \
		--host $(SQLDUMP_TEST_HOST) --port $(SQLDUMP_TEST_PORT) \
		--database $(SQLDUMP_TEST_DB) --user $(SQLDUMP_TEST_USER) \
		--password $(SQLDUMP_TEST_PASSWORD) \
		--output-dir build/e2e --templates-dir ./templates
	@echo "Generated inventory under build/e2e"

e2e-analyze: db-up  ## Run an online analysis against the test DB into ./build/analysis
	rm -rf build/analysis
	$(PYTHON) -m sql_dump.cli analyze \
		--host $(SQLDUMP_TEST_HOST) --port $(SQLDUMP_TEST_PORT) \
		--database $(SQLDUMP_TEST_DB) --user $(SQLDUMP_TEST_USER) \
		--password $(SQLDUMP_TEST_PASSWORD) \
		--output build/analysis --templates-dir ./templates --sample-size 10000
	@echo "Generated analysis under build/analysis"

clean:  ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
