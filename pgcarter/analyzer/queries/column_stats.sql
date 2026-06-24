-- column_stats.sql
-- Per-column null and cardinality profile. Read-only.
-- The column placeholder is a quoted identifier; the relation placeholder is a
-- FROM-clause expression (optionally a LIMIT sample subquery).
SELECT
    count(*)                                  AS total_rows,
    count(*) FILTER (WHERE {column} IS NULL)  AS null_rows,
    count(DISTINCT {column})                  AS distinct_values
FROM {relation}
