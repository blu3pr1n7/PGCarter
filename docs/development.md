# Development setup

## Repository setup

```bash
git clone git@github.com:blu3pr1n7/sql-dump.git
cd sql-dump
uv venv --python 3.12
uv pip install -e ".[dev]"
```

The `Makefile` wraps the common workflows:

```bash
make dev          # install with dev dependencies
make test         # unit tests (no database needed)
make lint         # ruff
make typecheck    # mypy
make coverage     # unit tests with coverage
```

## Running tests

```bash
make test                 # unit tests only
.venv/bin/python -m pytest -m "not integration"   # same, directly
```

### Integration tests (dockerised database)

A disposable PostgreSQL 16 instance is provided via `docker-compose.yml` (host
port **55432**, isolated from any local Postgres):

```bash
make db-up               # start the test DB and wait until healthy
make test-integration    # run integration tests against it
make e2e                 # run the index CLI end-to-end into ./build/e2e
make e2e-analyse         # run an online analysis into ./build/analysis
make test-all            # unit + integration
make db-down             # tear down (removes the data)
```

## Linting & formatting

```bash
make lint                 # ruff check
make format               # ruff format + ruff check --fix
make typecheck            # mypy sql_dump
```

Style: line length 100, ruff rule sets `E`, `F`, `I`, `UP`, `B`. All public
functions are typed (`mypy` runs with `disallow_untyped_defs`).

## Building the docs site locally

```bash
pip install -e ".[docs]"
mkdocs serve              # live-reload preview at http://127.0.0.1:8000
mkdocs build --strict     # production build (fails on warnings/broken links)
```

## Extending sql-dump

### Adding a new extractor

1. Add a metadata dataclass to `sql_dump/models/__init__.py` (the single source
   of truth shared by SQL generation, JSON, and templates).
2. Create `sql_dump/extractor/<asset>.py` subclassing `Extractor`, querying the
   catalogs and returning your model.
3. Wire it into `InventoryExtractor.extract()` in
   `sql_dump/extractor/__init__.py` (wrap the call in `_safe(...)` so a failure
   is recorded, not fatal).
4. Emit it from the writers (`sql_dump/writers/`) and add a template if it should
   appear in docs.
5. Add unit tests using the `FakeDB` pattern in `tests/test_extractors.py`.

### Adding a new analysis rule

Checks are plugin-style — adding one requires only a new class:

```python
from sql_dump.analyzer.models import WARNING, CheckResult
from sql_dump.analyzer.rules import ColumnCheck, register


@register
class MyCheck(ColumnCheck):
    name = "my_check"
    category = "column"

    def applies(self, asset, ctx) -> bool:
        table, column = asset
        return column.nullable

    def execute(self, asset, ctx) -> list[CheckResult]:
        table, column = asset
        return [self.result(severity=WARNING, message="...", table=table.qualified_name,
                            column=column.name)]
```

Subclass `TableCheck`, `ColumnCheck`, or `DatabaseCheck`, decorate with
`@register`, and the engine discovers it automatically. Any database access must
go through `ctx.run(sql)`, which validates the statement as read-only. Add tests
in `tests/test_analyzer.py`.

## See also

- [Contributing](contributing.md)
- [Architecture](architecture.md)
