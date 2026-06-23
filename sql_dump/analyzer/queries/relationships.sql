-- relationships.sql
-- Inbound foreign-key reference counts per table ("importance" / fan-in).
-- Read-only. The schemas placeholder is a SQL text-array literal of in-scope
-- schema names, e.g. ARRAY['public']::text[].
SELECT
    refn.nspname                  AS referenced_schema,
    refc.relname                  AS referenced_table,
    count(*)                      AS referenced_by
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class refc      ON refc.oid = con.confrelid
JOIN pg_catalog.pg_namespace refn  ON refn.oid = refc.relnamespace
WHERE con.contype = 'f'
  AND refn.nspname = ANY({schemas_literal})
GROUP BY refn.nspname, refc.relname
ORDER BY count(*) DESC, refc.relname
