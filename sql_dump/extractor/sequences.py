"""Sequence extraction."""

from __future__ import annotations

from ..models import Sequence
from .base import Extractor

_QUERY = """
SELECT
    s.schemaname                           AS schema,
    s.sequencename                         AS name,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    s.data_type::text                      AS data_type,
    s.start_value                          AS start,
    s.increment_by                         AS increment,
    s.min_value                            AS min_value,
    s.max_value                            AS max_value,
    s.cache_size                           AS cache,
    s.cycle                                AS cycle,
    (
        SELECT quote_ident(dn.nspname) || '.' || quote_ident(dc.relname)
               || '.' || a.attname
        FROM pg_catalog.pg_depend d
        JOIN pg_catalog.pg_class dc ON dc.oid = d.refobjid
        JOIN pg_catalog.pg_namespace dn ON dn.oid = dc.relnamespace
        JOIN pg_catalog.pg_attribute a
          ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
        WHERE d.objid = c.oid AND d.deptype IN ('a', 'i') AND d.refobjsubid > 0
        LIMIT 1
    )                                      AS owned_by,
    EXISTS (
        SELECT 1 FROM pg_catalog.pg_depend d
        WHERE d.objid = c.oid AND d.deptype = 'i' AND d.refobjsubid > 0
    )                                      AS is_identity
FROM pg_catalog.pg_sequences s
JOIN pg_catalog.pg_class c ON c.relname = s.sequencename
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname
WHERE s.schemaname = ANY(%(schemas)s)
ORDER BY s.schemaname, s.sequencename
"""


class SequenceExtractor(Extractor):
    name = "sequence"

    def extract(self) -> list[Sequence]:
        sequences = [
            Sequence(
                schema=r["schema"],
                name=r["name"],
                owner=r["owner"],
                data_type=r["data_type"],
                start=r["start"],
                increment=r["increment"],
                min_value=r["min_value"],
                max_value=r["max_value"],
                cache=r["cache"],
                cycle=r["cycle"],
                owned_by=r["owned_by"],
                is_identity=r["is_identity"],
            )
            for r in self.db.query(_QUERY, {"schemas": self.schemas})
        ]
        self.report.record_extracted("sequences", len(sequences))
        return sequences
