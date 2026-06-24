<p align="center">
  <img src="docs/assets/logo.png" alt="pgcarter" width="200">
</p>

<h1 align="center">pgcarter</h1>

<p align="center">
  <a href="https://github.com/blu3pr1n7/pgcarter/actions/workflows/ci.yml"><img src="https://github.com/blu3pr1n7/pgcarter/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://blu3pr1n7.github.io/pgcarter/"><img src="https://github.com/blu3pr1n7/pgcarter/actions/workflows/docs.yml/badge.svg" alt="Docs"></a>
  <a href="https://pypi.org/project/pgcarter/"><img src="https://img.shields.io/pypi/v/pgcarter.svg" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-green.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
</p>

A production-quality PostgreSQL **schema inventory, SQL extraction,
documentation generation, and database-shape analysis** tool. `pgcarter` is
both a schema extraction tool and a lightweight database discovery and
profiling platform.

📖 **Full documentation: <https://blu3pr1n7.github.io/PGCarter/>**

## Quick start

```bash
pip install -e .

# 1. Extract a schema inventory (SQL + JSON + docs)
pgcarter index --database mydb --output-dir ./inventory

# 2. Profile it offline (no database needed)
pgcarter analyze --input ./inventory/json --output ./analysis
```

`pgcarter` connects to a PostgreSQL database and produces three independent
outputs:

1. **Executable SQL** — deterministic, ordered PostgreSQL DDL files that can be
   run to recreate database structures (plus a single ordered `apply.sql`).
2. **Structured metadata** — JSON files describing every extracted asset.
3. **Documentation** — Markdown rendered entirely from user-provided Jinja2
   templates.

A fourth capability, the **`analyze` subcommand**, performs automated database
shape analysis — table sizes, column characteristics, data-quality indicators,
relationships, and schema-design patterns. See
[Database analysis & profiling](#database-analysis--profiling).

> **It never exports table data.** This is a schema and metadata extraction
> utility only — no `INSERT`, no `COPY`, no row contents. The analyzer is
> likewise read-only: every profiling query is a validated `SELECT`.

## Design boundaries

The two output layers are strictly separated:

- The **SQL generation layer** depends on metadata models only — never on
  templates.
- The **documentation layer** is entirely template-driven (Jinja2) and
  generates **no SQL**. No Markdown is embedded in Python source.

```
PostgreSQL ──▶ Extractors ──▶ Metadata Models ─┬─▶ SQL Generator ──▶ sql/
                                                └─▶ Jinja Renderer ──▶ docs/
                                                                  └──▶ json/
```

## Installation

Requires **Python 3.12+**. Uses [`psycopg`](https://www.psycopg.org/psycopg3/)
(psycopg3) and `jinja2`. No SQLAlchemy.

```bash
# with uv (recommended)
uv venv --python 3.12
uv pip install -e ".[dev]"

# or with pip
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

The CLI (built with [Typer](https://typer.tiangolo.com/)) has two subcommands:
`index` (schema extraction) and `analyze` (shape analysis & profiling).

```bash
pgcarter index \
  --host localhost \
  --port 5432 \
  --database mydb \
  --user postgres \
  --password secret \
  --output-dir ./inventory \
  --templates-dir ./templates
```

| Argument | Default | Notes |
| --- | --- | --- |
| `--host` | `localhost` | |
| `--port` | `5432` | |
| `--database` | _(required)_ | |
| `--user` | `postgres` | |
| `--password` | — | falls back to `PGPASSWORD` |
| `--output-dir` | _the database name_ | created if missing; must be writable |
| `--templates-dir` | `./templates` | must exist for docs to be generated |
| `--schema` | `public` | repeatable; architecture supports multiple schemas |
| `--log-level` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` (or `LOG_LEVEL`) |
| `--pretty` / `--no-pretty` | JSON | colourised console logs for local dev (or `LOG_PRETTY`) |

The same `--log-level` / `--pretty` options apply to every subcommand.

The connection never writes: it issues `SET default_transaction_read_only = on`.

## Output structure

```
inventory/
├── sql/
│   ├── apply.sql                 # full schema, dependency-ordered, one run
│   ├── database.sql
│   ├── extensions.sql
│   ├── roles.sql
│   └── schemas/
│       ├── public.sql
│       └── public/
│           ├── tables/        indexes/        functions/
│           ├── views/         triggers/       sequences/
│           └── permissions/
├── json/
│   ├── database.json   schemas.json   tables.json   indexes.json
│   ├── views.json      functions.json triggers.json sequences.json
│   ├── extensions.json roles.json     permissions.json
│   ├── relationships.json
│   ├── relationships.dot         # Graphviz relationship graph
│   ├── schemas/<schema>.json
│   └── tables/<table>.json
├── docs/
│   ├── index.md   database.md   roles.md   permissions.md
│   └── schemas/<schema>/{schema.md, tables/, views/, functions/, triggers/, indexes/}
└── report.json                   # extracted / skipped / warnings / errors
```

Every SQL file starts with a provenance header:

```sql
-- Generated by pgcarter
-- Database: <database>
-- Object: <object>
-- Generated: <timestamp>
```

Every generated document starts with the equivalent HTML-comment header.

### `apply.sql` — guaranteed executable

Individual object files are executable when applied in dependency order. For
convenience `sql/apply.sql` is a single, dependency-ordered script
(extensions → roles → schemas → sequences → tables (FK-sorted) → sequence
ownership → indexes → views (dependency-sorted) → functions → triggers →
grants) that recreates the whole schema in one run. Role creation is guarded so
the script is re-runnable. This is exercised by the integration suite, which
replays `apply.sql` into a fresh database.

## Extraction scope

Reads from PostgreSQL system catalogs (`pg_catalog`) and `information_schema`.
Extracts: database, schemas, tables (columns, types, defaults, nullability,
identity and generated columns, comments), constraints (PK/FK/unique/check/
exclusion), indexes (incl. partial & expression), views & materialized views,
functions & procedures (signature, parameters, return type, language,
volatility, security mode, owner), triggers, sequences, extensions, roles
(attributes, memberships), privileges (database/schema/table/column/sequence/
function), and a relationship graph (foreign keys, view/trigger/sequence
dependencies).

Default scope is the `public` schema; pass `--schema` (repeatable) for others.

## Documentation templates

Documentation is **completely template-driven**. Templates are discovered
dynamically — if a template is missing, a warning is logged and processing
continues. Provide a `templates/` directory:

```
templates/
├── index.md.j2        # home page (database overview)
├── database.md.j2     # database detail
├── schema.md.j2       # per schema
├── table.md.j2        # per table
├── indexes.md.j2      # per-schema index overview
├── function.md.j2     # per function/procedure
├── view.md.j2         # per view / materialized view
├── trigger.md.j2      # per trigger
├── permissions.md.j2  # privilege matrix
└── roles.md.j2        # roles
```

> Note: the spec lists `index.md.j2` twice. Here `index.md.j2` is the home page
> and `indexes.md.j2` renders the per-schema index overview, avoiding the
> filename collision.

Templates receive the full structured context (`database`, `schemas`, `tables`,
`indexes`, `views`, `functions`, `triggers`, `sequences`, `extensions`,
`roles`, `permissions`, `relationships`, `generated_at`) plus object-specific
variables (e.g. `table`, `function`, `schema_tables`).

## Error handling

Connection failures, insufficient privileges, and unsupported objects are
handled gracefully: a failure in one extractor is captured and the run
continues. Everything is summarised in `report.json`:

```json
{
  "database": "mydb",
  "summary": { "extracted": {"tables": 120}, "skipped_count": 1,
               "warning_count": 0, "error_count": 0, "generated_file_count": 412 },
  "skipped": [], "warnings": [], "errors": [], "generated_files": []
}
```

Exit codes: `0` success, `2` completed with recorded errors, `1` fatal error.

## Database analysis & profiling

The `analyze` subcommand turns the inventory into an understanding of the
database's *shape*: what kinds of datasets exist, how big tables are, column
characteristics, data-quality signals, relationships, and likely design issues.
It is **not** a data dump — it profiles structure and statistics.

The existing JSON inventory is the analyzer's first input source, so it runs in
two modes.

### Offline mode (structure only, no database)

Analyze an existing JSON inventory with no connection. Identifies possible
checks from table structure, column names, data types, constraints,
relationships, and indexes — and records the exact read-only SQL each check
*would* run online.

```bash
pgcarter analyze --input ./inventory/json
```

### Online mode (connect and profile)

Connects to PostgreSQL and enriches the structural analysis with row counts,
null statistics, cardinality estimates, value distributions, freshness checks,
and size metrics.

```bash
pgcarter analyze \
  --database mydb \
  --schema public \
  --output ./analysis \
  --sample-size 10000
```

| Argument | Default | Notes |
| --- | --- | --- |
| `--input` | — | JSON inventory directory → **offline** mode |
| `--database` | — | connect & profile → **online** mode |
| `--host`/`--port`/`--user`/`--password` | localhost/5432/postgres/`PGPASSWORD` | online connection |
| `--schema` | `public` | repeatable |
| `--output` | `./analysis` | output directory |
| `--templates-dir` | `./templates` | Jinja2 templates for analysis docs |
| `--config` | — | analysis YAML (enabled checks, thresholds) |
| `--sample-size` | — | row cap for expensive per-column scans |
| `--statement-timeout` | `0` | per-query timeout (ms); an overrun is logged and skipped |

Provide `--input` (offline), `--database` (online), or both (use the JSON as the
inventory base while connecting for statistics).

### Output

```
analysis/
├── report.json          # full analysis (tables, metrics, checks, warnings)
├── report.md            # human-readable summary (rendered from a template)
├── warnings.json        # every non-informational finding
├── tables/
│   ├── users.json       # per-table metrics, columns, checks
│   └── orders.json
├── run-report.json      # run summary (extracted counts / errors)
└── docs/analysis/
    ├── index.md         # rendered overview
    ├── warnings.md
    └── tables/<table>.md
```

A worked example lives in [`examples/analysis/`](examples/analysis/).

### Checks

Checks are plugin-style: each is a class registered with `@register`, and
adding a new check requires nothing more than dropping a new class into the
relevant `pgcarter/analyzer/checks/` module. Categories:

- **Tables** — `table_size`, `row_count` (empty / extremely large), and
  `growth_indicators` (freshness window from `created_at`/`updated_at`/…),
  plus structural `table_structure` (missing primary key, very wide tables).
- **Columns** — `null_analysis`, `cardinality` (unique identifiers, low
  cardinality, text enums), `distribution` (min/max/avg), `string_profiling`
  (avg/min/max length), and name heuristics: `identifier_detection`,
  `timestamp_detection`, `email_detection`, `status_columns`,
  `suspicious_columns`.
- **Indexes** — `duplicate_indexes`, `missing_fk_indexes`, `unused_indexes`.
- **Relationships** — `heavily_referenced` (fan-in importance),
  `relationship_depth`, `orphan_relationships` (rows with a missing parent).
- **Quality** — `duplicate_primary_keys`, `duplicate_unique_values`,
  `unused_tables`.

Each finding has a severity (`info`/`warning`/`critical`); warnings and
criticals are collected into `warnings.json`.

### Resilience & progress

Online runs degrade gracefully. A table the connecting role cannot read
(`permission denied`), a missing object, or a query that exceeds
`--statement-timeout` is **logged as a single warning and skipped** — recorded
under `skipped` in `run-report.json`, never escalated to a run error (the exit
code stays `0`). The denied relation is remembered, so its remaining columns are
skipped without further round trips, and it still receives structural analysis.
Per-table progress is logged (`[n/N] analyzing …`) so long runs are observable.

For large databases, prefer `--sample-size` (bounds per-column scans) and
`--statement-timeout` (caps any single query); together they keep a run bounded
and visible.

### Query safety & performance

Every generated query is mechanically validated to be a single read-only
`SELECT`/`WITH` with no `INSERT`/`UPDATE`/`DELETE`/`DROP`/`TRUNCATE`/`ALTER`/…
(see `pgcarter/analyzer/queries.py::assert_safe`). Identifiers are quoted and
schema-qualified. Row-count and size checks prefer PostgreSQL's own statistics
(`pg_class.reltuples`, `pg_total_relation_size`) over scanning, and
`--sample-size N` bounds expensive per-column aggregates with a `LIMIT`
subquery. Identical queries from different checks share one round trip.

### Configuration

```yaml
analysis:
  enabled_checks:        # omit to run every check
    - null_analysis
    - cardinality
    - table_size
  thresholds:
    high_null_percentage: 80
    low_cardinality_limit: 10
    large_table_rows: 10000000
    unique_ratio: 0.99
    long_text_length: 10000
  # sample_size: 10000   # --sample-size overrides
```

```bash
pgcarter analyze --input ./inventory/json --config analysis.yml
```

A ready-to-edit example is in [`analysis.yml`](analysis.yml).

### Analysis templates

Like the rest of the project, analysis documentation is **completely
template-driven** — no Markdown is embedded in Python. Add to `templates/`:

```
templates/
├── analysis.md.j2          # overview (report.md + docs/analysis/index.md)
├── table_analysis.md.j2    # per table
├── column_analysis.md.j2   # per-column fragment (included by table_analysis)
└── warnings.md.j2          # warnings list
```

## Logging

Logging is built on [`structlog`](https://www.structlog.org/). The default is
**structured JSON on stdout**, ready for log aggregators (Datadog, ELK/
OpenSearch, CloudWatch, Loki, …):

```json
{"event": "database_connecting", "host": "localhost", "database": "mydb",
 "level": "info", "logger": "pgcarter.extractor.connection",
 "timestamp": "2026-06-23T10:30:00.123456Z"}
```

For local development, enable colourised console output:

```bash
pgcarter index --database mydb --pretty
# or, for any process:
LOG_PRETTY=true LOG_LEVEL=DEBUG pgcarter analyze --input ./inventory/json
```

```
2026-06-23T10:30:00Z [info] database_connecting host=localhost database=mydb
```

Configuration:

| Source | Production (default) | Local dev |
| --- | --- | --- |
| CLI flag | `--no-pretty` | `--pretty` |
| Env var | `LOG_PRETTY=false` | `LOG_PRETTY=true` |
| Level | `--log-level` / `LOG_LEVEL` (default `INFO`) | |

### Using it in code

Setup happens once, in `pgcarter/logging_config.py`:

```python
from pgcarter.logging_config import configure_logging, get_logger

configure_logging(pretty_logs=False, level="INFO")  # JSON to stdout
log = get_logger(__name__)
log.info("user_created", user_id=123, plan="enterprise")   # structured
log.exception("payment_failed", payment_id=123)            # structured traceback
```

Both **stdlib** `logging.getLogger(...)` and **structlog** `get_logger(...)`
render through the same pipeline, so existing `log.info("Extracting %s", x)`
calls keep working alongside structured events.

Attach request/job correlation (or any global metadata) with contextvars — it is
added to every subsequent event automatically:

```python
import structlog
structlog.contextvars.bind_contextvars(service="pgcarter", request_id="abc123")
```

> Never log secrets, tokens, or sensitive row data — logging stays advisory and
> metadata-only, like the rest of the tool.

## Documentation site

The project documentation (this README's content plus installation, usage, CLI,
architecture, and API reference) is published with **MkDocs Material** to GitHub
Pages: <https://blu3pr1n7.github.io/pgcarter/>.

Build or preview it locally:

```bash
pip install -e ".[docs]"
make docs-serve     # live preview at http://127.0.0.1:8000
make docs-build     # strict build (fails on warnings/broken links)
```

The `.github/workflows/docs.yml` workflow builds the site with
`mkdocs build --strict` and deploys it on every push to `master`.

> **One-time manual step:** GitHub Pages must be set to publish from GitHub
> Actions before the first deploy. In the repository, go to
> **Settings → Pages → Build and deployment** and set **Source** to
> **“GitHub Actions”**. (This cannot be enabled from the workflow itself; it is
> a repository setting.) Once set, the `docs` workflow publishes automatically.

## Development

```bash
make dev          # install with dev dependencies
make test         # unit tests (no database needed)
make lint         # ruff
make typecheck    # mypy
make coverage     # unit tests with coverage
```

### Integration / e2e tests (dockerised database)

A dedicated, disposable PostgreSQL 16 instance is provided via
`docker-compose.yml` (host port **55432**, isolated from any other local
Postgres). The seed schema in `tests/fixtures/seed.sql` exercises every asset
category.

```bash
make db-up             # start the test DB and wait until healthy
make test-integration  # run integration tests against it
make e2e               # run the index CLI end-to-end into ./build/e2e
make e2e-analyze       # run an online analysis into ./build/analysis
make test-all          # unit + integration
make db-down           # tear down (removes the data)
```

The integration suite asserts that no row data is ever emitted and that the
generated `apply.sql` replays cleanly into a fresh database.

## Project layout

```
pgcarter/
├── cli.py            # Typer entry point (index + analyze subcommands)
├── config.py         # configuration + defaults
├── main.py           # orchestration
├── report.py         # run report
├── logging_config.py # structured logging
├── models/           # dataclass metadata models (single source of truth)
├── extractor/        # one module per asset category + orchestrator
├── sql/              # deterministic DDL generation (template-free)
├── docs/             # Jinja2 renderer (no SQL)
├── writers/          # SQL / JSON / DOT / apply.sql writers
└── analyzer/         # database shape analysis & profiling
    ├── runner.py     #   analyze orchestration (offline/online)
    ├── config.py     #   analysis config (enabled checks, thresholds)
    ├── models.py     #   analysis result models
    ├── heuristics.py #   column name/type semantics
    ├── queries.py    #   read-only SQL builders + safety guard
    ├── queries/      #   *.sql templates (table_stats, column_stats, relationships)
    ├── rules.py      #   Check base, registry, AnalysisContext
    ├── checks/       #   plugin checks: tables/columns/indexes/relationships/quality/statistics
    ├── engine.py     #   runs checks, assembles the report
    ├── loader.py     #   reconstruct an Inventory from JSON (offline input)
    └── writer.py     #   analysis JSON + Jinja2 docs
```
