"""Schema metadata extraction."""

from __future__ import annotations

from ..models import Schema
from .base import Extractor

_QUERY = """
SELECT
    n.nspname                              AS name,
    pg_catalog.pg_get_userbyid(n.nspowner) AS owner,
    pg_catalog.obj_description(n.oid, 'pg_namespace') AS comment
FROM pg_catalog.pg_namespace n
WHERE n.nspname = ANY(%(schemas)s)
ORDER BY n.nspname
"""


class SchemaExtractor(Extractor):
    name = "schema"

    def extract(self) -> list[Schema]:
        rows = self.db.query(_QUERY, {"schemas": self.schemas})
        schemas = [
            Schema(name=r["name"], owner=r["owner"], comment=r["comment"])
            for r in rows
        ]
        self.report.record_extracted("schemas", len(schemas))
        return schemas
