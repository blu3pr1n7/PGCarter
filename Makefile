.PHONY: help install dev lint format format-check typecheck ci test test-unit \
        test-integration test-all coverage clean run analyze db-up db-down \
        db-logs db-psql e2e e2e-analyze docs docs-serve docs-build

PYTHON ?= .venv/bin/python
UV ?= uv
COMPOSE ?= docker compose

# Connection details for the dockerised test database (see docker-compose.yml).
export PGCARTER_TEST_HOST ?= localhost
export PGCARTER_TEST_PORT ?= 55432
export PGCARTER_TEST_DB   ?= pgcarter_test
export PGCARTER_TEST_USER ?= pgcarter
export PGCARTER_TEST_PASSWORD ?= pgcarter

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	$(UV) pip install -e .

dev:  ## Install the package with dev dependencies
	$(UV) pip install -e ".[dev]"

lint:  ## Run ruff lint checks
	$(PYTHON) -m ruff check pgcarter tests

format:  ## Auto-format with ruff
	$(PYTHON) -m ruff format pgcarter tests
	$(PYTHON) -m ruff check --fix pgcarter tests

format-check:  ## Verify formatting without changing files (CI gate)
	$(PYTHON) -m ruff format --check pgcarter tests

typecheck:  ## Run mypy
	$(PYTHON) -m mypy pgcarter

ci:  ## Run the fast CI gate locally (lint + format check + types + unit)
	$(PYTHON) -m ruff check pgcarter tests
	$(PYTHON) -m ruff format --check pgcarter tests
	$(PYTHON) -m mypy pgcarter
	$(PYTHON) -m pytest -m "not integration"

test: test-unit  ## Run the unit test suite (alias)

test-unit:  ## Run unit tests (no database required)
	$(PYTHON) -m pytest -m "not integration"

test-integration: db-up  ## Start the test DB and run integration tests
	$(PYTHON) -m pytest -m integration

test-all: db-up  ## Run the full suite (unit + integration) against the test DB
	$(PYTHON) -m pytest

coverage:  ## Run tests with coverage report
	$(PYTHON) -m pytest -m "not integration" --cov=pgcarter --cov-report=term-missing

run:  ## Run pgcarter index (pass ARGS="--database mydb ...")
	$(PYTHON) -m pgcarter.cli index $(ARGS)

analyze:  ## Run pgcarter analyze (pass ARGS="--input ./json ..." or "--database ...")
	$(PYTHON) -m pgcarter.cli analyze $(ARGS)

# --- Dockerised test database ----------------------------------------------

db-up:  ## Start the test PostgreSQL and wait until healthy
	$(COMPOSE) up -d --wait

db-down:  ## Stop and remove the test PostgreSQL (and its data)
	$(COMPOSE) down -v

db-logs:  ## Tail the test database logs
	$(COMPOSE) logs -f postgres

db-psql:  ## Open a psql shell in the test database
	$(COMPOSE) exec postgres psql -U $(PGCARTER_TEST_USER) -d $(PGCARTER_TEST_DB)

e2e: db-up  ## Run the index CLI end-to-end against the test DB into ./build/e2e
	rm -rf build/e2e
	$(PYTHON) -m pgcarter.cli index \
		--host $(PGCARTER_TEST_HOST) --port $(PGCARTER_TEST_PORT) \
		--database $(PGCARTER_TEST_DB) --user $(PGCARTER_TEST_USER) \
		--password $(PGCARTER_TEST_PASSWORD) \
		--output-dir build/e2e --templates-dir ./templates
	@echo "Generated inventory under build/e2e"

e2e-analyze: db-up  ## Run an online analysis against the test DB into ./build/analysis
	rm -rf build/analysis
	$(PYTHON) -m pgcarter.cli analyze \
		--host $(PGCARTER_TEST_HOST) --port $(PGCARTER_TEST_PORT) \
		--database $(PGCARTER_TEST_DB) --user $(PGCARTER_TEST_USER) \
		--password $(PGCARTER_TEST_PASSWORD) \
		--output build/analysis --templates-dir ./templates --sample-size 10000
	@echo "Generated analysis under build/analysis"

# --- Documentation site -----------------------------------------------------

docs:  ## Install the documentation toolchain
	$(UV) pip install -e ".[docs]"

docs-serve:  ## Live-reload docs preview at http://127.0.0.1:8000
	$(PYTHON) -m mkdocs serve

docs-build:  ## Build the docs site (strict: fails on warnings/broken links)
	$(PYTHON) -m mkdocs build --strict

clean:  ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache site
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
