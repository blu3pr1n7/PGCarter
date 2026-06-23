"""Database-level metadata extraction."""

from __future__ import annotations

from sql_dump.extractor.base import Extractor
from sql_dump.models import DatabaseInfo

_QUERY = """
SELECT
    d.datname                                   AS name,
    pg_catalog.pg_encoding_to_char(d.encoding)  AS encoding,
    d.datcollate                                AS collation,
    d.datctype                                  AS ctype,
    pg_catalog.pg_get_userbyid(d.datdba)        AS owner,
    pg_catalog.shobj_description(d.oid, 'pg_database') AS comment,
    current_setting('server_version')           AS version
FROM pg_catalog.pg_database d
WHERE d.datname = current_database()
"""


class DatabaseExtractor(Extractor):
    name = "database"

    def extract(self) -> DatabaseInfo:
        row = self.db.query_one(_QUERY)
        if row is None:  # pragma: no cover - current_database always resolves
            raise RuntimeError("Could not resolve current database metadata")
        info = DatabaseInfo(
            name=row["name"],
            version=row["version"],
            encoding=row["encoding"],
            collation=row["collation"],
            ctype=row["ctype"],
            owner=row["owner"],
            comment=row["comment"],
        )
        self.report.record_extracted("database", 1)
        return info
