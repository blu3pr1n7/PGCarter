# CLI reference

The CLI is built with [Typer](https://typer.tiangolo.com/). Run any command with
`--help` for the authoritative, always-current list of options:

```bash
sql-dump --help
sql-dump index --help
sql-dump analyze --help
```

## Global behaviour

- **Logging** options (`--log-level`, `--pretty/--no-pretty`) apply to every
  subcommand. JSON to stdout is the default; `--pretty` (or `LOG_PRETTY=true`)
  enables colourised console output. See
  [Configuration → Logging](configuration.md#logging).
- **Exit codes**: `0` success, `2` completed with recorded errors, `1` fatal
  error. (`2` is also returned for command-line usage errors.)

## `sql-dump index`

Extract a PostgreSQL schema inventory (SQL + JSON + docs).

```bash
sql-dump index --database mydb --output-dir ./inventory --templates-dir ./templates
```

| Option | Default | Description |
| --- | --- | --- |
| `--database` | _(required)_ | Database name to inventory |
| `--host` | `localhost` | Database host |
| `--port` | `5432` | Database port |
| `--user` | `postgres` | Database user |
| `--password` | — | Database password (falls back to `PGPASSWORD`) |
| `--output-dir` | _the database name_ | Output directory (created if missing) |
| `--templates-dir` | `./templates` | Jinja2 templates directory (must exist for docs) |
| `--schema` | `public` | Schema to extract (repeatable) |
| `--log-level` | `INFO` (or `LOG_LEVEL`) | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `--pretty` / `--no-pretty` | JSON (or `LOG_PRETTY`) | Colourised console logs |

## `sql-dump analyze`

Analyze a database's shape: structure offline (from a JSON inventory) or
statistics online (connecting to PostgreSQL).

```bash
# offline
sql-dump analyze --input ./inventory/json --output ./analysis

# online
sql-dump analyze --database mydb --output ./analysis --sample-size 10000
```

| Option | Default | Description |
| --- | --- | --- |
| `--input` | — | JSON inventory directory → **offline** mode |
| `--database` | — | Connect & profile → **online** mode |
| `--host` | `localhost` | Database host |
| `--port` | `5432` | Database port |
| `--user` | `postgres` | Database user |
| `--password` | — | Database password (falls back to `PGPASSWORD`) |
| `--schema` | `public` | Schema to analyze (repeatable) |
| `--output` | `./analysis` | Output directory |
| `--templates-dir` | `./templates` | Jinja2 templates directory |
| `--config` | — | Analysis configuration YAML (enabled checks, thresholds) |
| `--sample-size` | — | Row cap for expensive per-column scans |
| `--statement-timeout` | `0` | Per-query timeout (ms) for online profiling (`0` = none) |
| `--log-level` | `INFO` (or `LOG_LEVEL`) | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `--pretty` / `--no-pretty` | JSON (or `LOG_PRETTY`) | Colourised console logs |

Provide `--input` (offline), `--database` (online), or both (use the JSON as the
inventory base while connecting for statistics). Providing neither is a usage
error.

## Available analysis checks

Enable a subset via `--config` (`analysis.enabled_checks`); omit to run all.

- **Tables** — `table_size`, `row_count`, `growth_indicators`, `table_structure`
- **Columns** — `null_analysis`, `cardinality`, `distribution`,
  `string_profiling`, `identifier_detection`, `timestamp_detection`,
  `email_detection`, `status_columns`, `suspicious_columns`
- **Indexes** — `duplicate_indexes`, `missing_fk_indexes`, `unused_indexes`
- **Relationships** — `heavily_referenced`, `relationship_depth`,
  `orphan_relationships`
- **Quality** — `duplicate_primary_keys`, `duplicate_unique_values`,
  `unused_tables`
