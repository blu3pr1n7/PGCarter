# Analysis: public.audit_log

## Metrics

| Metric | Value |
| --- | --- |
| Columns | 4 |

## Columns

| Column | Type | Nullable | Semantics | Notes |
| --- | --- | :---: | --- | --- |
| `id` | `bigint` | no | identifier |  |
| `table_name` | `text` | no |  |  |
| `action` | `text` | no |  |  |
| `at` | `timestamp with time zone` | no |  |  |

## Findings

- **WARNING** [unused_tables] — Table participates in no foreign-key relationships
