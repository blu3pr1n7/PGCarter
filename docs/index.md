# pgcarter

A production-quality PostgreSQL **schema inventory, SQL extraction,
documentation generation, and database shape-analysis** tool — a lightweight
PostgreSQL discovery and profiling platform.

!!! note "Read-only by design"
    `pgcarter` extracts schema and metadata only. It **never** exports table
    data — no `INSERT`, no `COPY`, no row contents — and every analysis query is
    a validated read-only `SELECT`.

## What it does

`pgcarter` connects to a PostgreSQL database and produces independent,
composable outputs:

| Output | Description |
| --- | --- |
| **Executable SQL** | Deterministic, dependency-ordered DDL files (plus a single `apply.sql`) that recreate the database structure. |
| **Structured metadata** | JSON describing every extracted asset. |
| **Documentation** | Markdown rendered entirely from user-provided Jinja2 templates. |
| **Shape analysis** | Table sizes, column characteristics, data-quality signals, relationships, and schema-design patterns. |

## Entrypoints

The CLI exposes two subcommands:

```text
pgcarter
   ├── index     # schema extraction → SQL + JSON + docs
   └── analyze   # dataset profiling → statistics, quality checks, warnings
```

- **`pgcarter index`** — discover database structure and emit SQL, JSON, and
  documentation. See [Usage](usage.md#index-schema-extraction).
- **`pgcarter analyze`** — profile datasets offline (from a JSON inventory) or
  online (connecting for statistics). See
  [Usage](usage.md#analyze-shape-analysis-profiling).

## Supported PostgreSQL features

Reads from system catalogs (`pg_catalog`) and `information_schema` and extracts:
database, schemas, tables (columns, types, defaults, nullability, identity and
generated columns, comments), constraints (PK/FK/unique/check/exclusion), indexes
(including partial and expression indexes), views and materialized views,
functions and procedures, triggers, sequences, extensions, roles, privileges,
and a relationship graph.

## Design goals

- **Separation of concerns** — SQL generation depends on metadata models only;
  documentation is entirely template-driven (no Markdown embedded in Python).
- **Read-only and safe** — the connection issues
  `SET default_transaction_read_only = on`; analysis queries are validated as
  pure `SELECT`s.
- **Resilient** — a failure in one extractor or check is captured and the run
  continues, summarised in a report.
- **Deterministic** — repeated runs against an unchanged database yield
  byte-identical SQL (modulo the timestamp header).

## Next steps

- [Installation](installation.md)
- [Usage](usage.md)
- [Configuration](configuration.md)
- [Architecture](architecture.md)
