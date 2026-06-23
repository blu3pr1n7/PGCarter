"""Index extraction."""

from __future__ import annotations

from ..models import Index
from .base import Extractor

_QUERY = """
SELECT
    n.nspname                              AS schema,
    ic.relname                             AS name,
    tc.relname                             AS table,
    pg_catalog.pg_get_indexdef(i.indexrelid, 0, true) AS definition,
    i.indisunique                          AS is_unique,
    i.indisprimary                         AS is_primary,
    am.amname                              AS method,
    pg_catalog.pg_get_expr(i.indpred, i.indrelid, true) AS predicate,
    (
        SELECT array_agg(a.attname ORDER BY k.ord)
        FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_catalog.pg_attribute a
          ON a.attrelid = i.indrelid AND a.attnum = k.attnum
        WHERE k.attnum <> 0
    )                                      AS columns,
    EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint con
        WHERE con.conindid = i.indexrelid
    )                                      AS is_constraint,
    (i.indexprs IS NOT NULL)               AS has_expressions
FROM pg_catalog.pg_index i
JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid
JOIN pg_catalog.pg_class tc ON tc.oid = i.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = ic.relnamespace
JOIN pg_catalog.pg_am am ON am.oid = ic.relam
WHERE n.nspname = ANY(%(schemas)s)
ORDER BY n.nspname, tc.relname, ic.relname
"""


class IndexExtractor(Extractor):
    name = "index"

    def extract(self) -> list[Index]:
        rows = self.db.query(_QUERY, {"schemas": self.schemas})
        indexes = [
            Index(
                schema=r["schema"],
                name=r["name"],
                table=r["table"],
                definition=r["definition"],
                is_unique=r["is_unique"],
                is_primary=r["is_primary"],
                is_constraint=r["is_constraint"],
                method=r["method"],
                columns=list(r["columns"] or []),
                predicate=r["predicate"],
            )
            for r in rows
        ]
        self.report.record_extracted("indexes", len(indexes))
        return indexes
