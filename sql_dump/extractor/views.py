"""View and materialized view extraction."""

from __future__ import annotations

from sql_dump.extractor.base import Extractor
from sql_dump.models import View

_QUERY = """
SELECT
    n.nspname                              AS schema,
    c.relname                              AS name,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    (c.relkind = 'm')                      AS materialized,
    pg_catalog.pg_get_viewdef(c.oid, true) AS definition,
    pg_catalog.obj_description(c.oid, 'pg_class') AS comment,
    (
        SELECT array_agg(a.attname ORDER BY a.attnum)
        FROM pg_catalog.pg_attribute a
        WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    )                                      AS columns
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('v', 'm')
  AND n.nspname = ANY(%(schemas)s)
ORDER BY n.nspname, c.relname
"""


class ViewExtractor(Extractor):
    name = "view"

    def extract(self) -> list[View]:
        rows = self.db.query(_QUERY, {"schemas": self.schemas})
        views = [
            View(
                schema=r["schema"],
                name=r["name"],
                owner=r["owner"],
                definition=(r["definition"] or "").strip(),
                materialized=r["materialized"],
                comment=r["comment"],
                columns=list(r["columns"] or []),
            )
            for r in rows
        ]
        self.report.record_extracted("views", len(views))
        return views
