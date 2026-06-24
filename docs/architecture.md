# Architecture

`pgcarter` is organised as a pipeline with strictly separated layers. The
metadata models are the single source of truth shared by every downstream
consumer.

## High-level flow

```text
PostgreSQL
    |
    v
Extractors            (pgcarter/extractor/)
    |
    v
Metadata Models       (pgcarter/models/)
    |
    +----------------+----------------+
    |                |                |
    v                v                v
SQL Generator     JSON Writer     Documentation
(pgcarter/sql/)   (writers/)      (docs/ renderer, Jinja2)
    |
    v
Analyzer              (pgcarter/analyzer/)
```

## Design boundaries

- The **SQL generation layer** depends on metadata models only — never on
  templates. Output is deterministic.
- The **documentation layer** is entirely template-driven (Jinja2) and generates
  **no SQL**. No Markdown is embedded in Python source.
- The **analyzer** consumes the same models and, in offline mode, the JSON
  inventory the writer produced — so analysis needs no database at all.

## Package layout

```text
pgcarter/
├── cli.py            # Typer entry point (index + analyze subcommands)
├── config.py         # configuration + defaults
├── main.py           # extraction orchestration
├── report.py         # run report (extracted / skipped / warnings / errors)
├── logging_config.py # structlog-based structured logging
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
    ├── queries/      #   *.sql templates
    ├── rules.py      #   Check base, registry, AnalysisContext
    ├── checks/       #   plugin checks (tables/columns/indexes/…)
    ├── engine.py     #   runs checks, assembles the report
    ├── loader.py     #   reconstruct an Inventory from JSON (offline input)
    └── writer.py     #   analysis JSON + Jinja2 docs
```

## Extraction

The `InventoryExtractor` runs each category extractor in turn. A failure in one
extractor is captured in the run report and does not abort the run, so a database
the connecting role can only partially read still yields a best-effort inventory.
Queries are batched per asset category to scale to databases with hundreds of
tables.

## Analysis

Checks are **plugin-style**: each is a class registered with `@register` in
`pgcarter/analyzer/rules.py`. The engine feeds each asset to the checks whose
scope matches it — tables to table checks, `(table, column)` pairs to column
checks, the whole inventory to database checks — then merges results into the
report. Every analysis query is validated read-only before execution
(`assert_safe`), and permission/timeout errors are logged-and-skipped rather than
failing the run.

## Safety model

- The extraction connection sets `default_transaction_read_only = on`.
- Analysis SQL is constructed from quoted, schema-qualified identifiers and
  validated to be a single `SELECT`/`WITH` — no `INSERT`/`UPDATE`/`DELETE`/
  `DROP`/`TRUNCATE`/`ALTER`/…
- Row data is never emitted: outputs are DDL and metadata only.

## See also

- [Development](development.md) — how to add a new extractor or analysis rule
- [API reference](reference.md) — generated from docstrings
