-- table_stats.sql
-- Size metrics and the planner's estimated row count for a single relation.
-- Read-only. Placeholders are substituted with quoted string literals
-- (schema name, table name, and qualified name passed to the pg_*_size calls).
SELECT
    pg_total_relation_size({relation_literal})                 AS total_bytes,
    pg_table_size({relation_literal})                          AS table_bytes,
    pg_indexes_size({relation_literal})                        AS index_bytes,
    pg_size_pretty(pg_total_relation_size({relation_literal})) AS total_pretty,
    pg_size_pretty(pg_table_size({relation_literal}))          AS table_pretty,
    pg_size_pretty(pg_indexes_size({relation_literal}))        AS index_pretty,
    c.reltuples::bigint                                        AS estimated_rows
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = {schema_literal}
  AND c.relname = {table_literal}
