# Configuration

## Connection

Connection options are passed as CLI flags (see the [CLI reference](cli.md)):

| Flag | Default | Notes |
| --- | --- | --- |
| `--host` | `localhost` | |
| `--port` | `5432` | |
| `--database` | required for `index`; enables online mode for `analyze` | |
| `--user` | `postgres` | |
| `--password` | — | falls back to the `PGPASSWORD` environment variable |
| `--schema` | `public` | repeatable; multiple schemas supported |

The password may be supplied with `--password` or via `PGPASSWORD`:

```bash
export PGPASSWORD=secret
pgcarter index --database mydb --user app
```

## Analysis configuration

`pgcarter analyze` accepts a YAML config selecting which checks run and tuning
thresholds:

```yaml
analysis:
  enabled_checks:        # omit to run every check
    - null_analysis
    - cardinality
    - table_size
  thresholds:
    high_null_percentage: 80      # flag columns at/above this null %
    low_cardinality_limit: 10     # distinct values at/below this -> "low cardinality"
    large_table_rows: 10000000    # estimated rows at/above this -> "extremely large"
    unique_ratio: 0.99            # distinct/total at/above this -> "identifier"
    long_text_length: 10000       # avg text length above this -> "wide text column"
  # sample_size: 10000            # --sample-size overrides this
```

```bash
pgcarter analyze --input ./inventory/json --config analysis.yml
```

A ready-to-edit example ships as `analysis.yml` in the repository root.

### Performance controls

| Flag | Purpose |
| --- | --- |
| `--sample-size N` | Bound expensive per-column scans with a `LIMIT N` subquery. |
| `--statement-timeout MS` | Per-query timeout (ms) for online profiling; a query that exceeds it is logged and skipped, never blocking the run. |

Row-count and size checks prefer PostgreSQL's own statistics
(`pg_class.reltuples`, `pg_total_relation_size`) over scanning, and identical
queries issued by different checks share a single round trip.

## Logging

Logging is built on [`structlog`](https://www.structlog.org/). The default is
**structured JSON on stdout**, suitable for log aggregators (Datadog,
ELK/OpenSearch, CloudWatch, Loki, …).

```json
{"event": "database_connecting", "host": "localhost", "database": "mydb",
 "level": "info", "logger": "pgcarter.extractor.connection",
 "timestamp": "2026-06-23T10:30:00.123456Z"}
```

For local development, enable colourised console output:

```bash
pgcarter index --database mydb --pretty
# or, for any invocation:
LOG_PRETTY=true LOG_LEVEL=DEBUG pgcarter analyze --input ./inventory/json
```

| Setting | Production (default) | Local dev |
| --- | --- | --- |
| CLI flag | `--no-pretty` | `--pretty` |
| Env var | `LOG_PRETTY=false` | `LOG_PRETTY=true` |
| Level | `--log-level` / `LOG_LEVEL` (default `INFO`) | |

Both stdlib `logging.getLogger(...)` and `structlog.get_logger(...)` render
through the same pipeline. Attach request/job correlation with contextvars:

```python
import structlog
structlog.contextvars.bind_contextvars(service="pgcarter", request_id="abc123")
```

!!! warning "Never log sensitive data"
    Logging stays advisory and metadata-only — no secrets, tokens, or row data.
