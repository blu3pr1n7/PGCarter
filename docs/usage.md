# Usage

`pgcarter` has two subcommands. Full flag references live in the
[CLI reference](cli.md).

## `index` — schema extraction

Connect to PostgreSQL and produce executable SQL, JSON metadata, and
template-driven documentation.

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

Purpose:

- database **schema extraction** (tables, columns, indexes, constraints,
  functions, triggers, sequences, roles, privileges, relationships)
- **SQL generation** — deterministic DDL plus a single ordered `apply.sql`
- **JSON inventory** — structured metadata for every asset

The connection never writes: it issues `SET default_transaction_read_only = on`.

### Output structure

```text
inventory/
├── sql/
│   ├── apply.sql                 # full schema, dependency-ordered, one run
│   ├── database.sql  extensions.sql  roles.sql
│   └── schemas/<schema>/{tables,indexes,functions,views,triggers,sequences,permissions}/
├── json/
│   ├── database.json  schemas.json  tables.json  indexes.json
│   ├── views.json  functions.json  triggers.json  sequences.json
│   ├── extensions.json  roles.json  permissions.json  relationships.json
│   ├── relationships.dot           # Graphviz relationship graph
│   ├── schemas/<schema>.json  tables/<table>.json
├── docs/
│   └── index.md  database.md  roles.md  permissions.md  schemas/<schema>/…
└── report.json                     # extracted / skipped / warnings / errors
```

The `json/` directory is the **input source for offline analysis** (below).

## `analyze` — shape analysis & profiling

Turn the inventory into an understanding of the database's shape: table sizes,
column characteristics, data-quality signals, relationships, and likely design
issues. It runs in two modes.

### Offline mode (structure only, no database)

Analyze an existing JSON inventory with no connection. Identifies possible
checks from structure, column names, types, constraints, relationships, and
indexes — and records the exact read-only SQL each check *would* run online.

```bash
pgcarter analyze --input ./inventory/json
```

### Online mode (connect and profile)

Connect to PostgreSQL and enrich the structural analysis with row counts, null
statistics, cardinality estimates, value distributions, freshness checks, and
size metrics.

```bash
pgcarter analyze \
  --database mydb \
  --schema public \
  --output ./analysis \
  --sample-size 10000
```

Purpose:

- **dataset profiling** — row counts, sizes, null rates, cardinality,
  distributions
- **table statistics** — preferring PostgreSQL's own `pg_class.reltuples` and
  `pg_total_relation_size` over scanning
- **quality checks** — duplicate keys, missing FK indexes, unused indexes,
  suspicious columns, orphaned relationships, and more

### Output structure

```text
analysis/
├── report.json          # full analysis (tables, metrics, checks, warnings)
├── report.md            # human-readable summary (rendered from a template)
├── warnings.json        # every non-informational finding
├── tables/<table>.json  # per-table metrics, columns, checks
├── run-report.json      # run summary (extracted counts / errors)
└── docs/analysis/       # index.md, warnings.md, tables/<table>.md
```

See [Configuration](configuration.md) for enabling/disabling checks and tuning
thresholds, sampling, and timeouts.

## Quick start

```bash
# 1. Extract a schema inventory
pgcarter index --database mydb --output-dir ./inventory

# 2. Profile it offline (no DB needed)
pgcarter analyze --input ./inventory/json --output ./analysis

# 3. Or profile online with sampling and a per-query timeout
pgcarter analyze --database mydb --output ./analysis \
  --sample-size 10000 --statement-timeout 15000
```

## Logging

Logs are structured JSON on stdout by default. For local development, add
`--pretty` (or set `LOG_PRETTY=true`) for colourised console output. See
[Configuration → Logging](configuration.md#logging).
