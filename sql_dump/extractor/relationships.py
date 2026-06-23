"""Relationship graph construction.

Edges are derived from already-extracted models (foreign keys, triggers,
sequence ownership) plus a catalog query for view dependencies.
"""

from __future__ import annotations

from sql_dump.extractor.base import Extractor
from sql_dump.models import Function, Relationship, Sequence, Table, Trigger

_VIEW_DEPS = """
SELECT DISTINCT
    dn.nspname || '.' || dependent.relname AS view,
    sn.nspname || '.' || source.relname    AS source
FROM pg_catalog.pg_depend d
JOIN pg_catalog.pg_rewrite rw ON rw.oid = d.objid
JOIN pg_catalog.pg_class dependent ON dependent.oid = rw.ev_class
JOIN pg_catalog.pg_namespace dn ON dn.oid = dependent.relnamespace
JOIN pg_catalog.pg_class source ON source.oid = d.refobjid
JOIN pg_catalog.pg_namespace sn ON sn.oid = source.relnamespace
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_class'::regclass
  AND dependent.relkind IN ('v', 'm')
  AND dependent.oid <> source.oid
  AND dn.nspname = ANY(%(schemas)s)
ORDER BY view, source
"""


class RelationshipExtractor(Extractor):
    name = "relationship"

    def build(
        self,
        tables: list[Table],
        triggers: list[Trigger],
        sequences: list[Sequence],
        functions: list[Function],
    ) -> list[Relationship]:
        edges: list[Relationship] = []

        # Foreign keys
        for table in tables:
            for con in table.constraints:
                if con.type == "FOREIGN KEY" and con.referenced_table:
                    target = f"{con.referenced_schema}.{con.referenced_table}"
                    edges.append(
                        Relationship(
                            source=table.qualified_name,
                            target=target,
                            type="foreign_key",
                            label=con.name,
                        )
                    )

        # Triggers depend on their table and trigger function
        for trig in triggers:
            table_ref = f"{trig.schema}.{trig.table}"
            edges.append(
                Relationship(source=table_ref, target=trig.name, type="trigger",
                             label=trig.name)
            )
            if trig.function:
                edges.append(
                    Relationship(source=trig.name, target=trig.function,
                                 type="trigger_dependency", label="executes")
                )

        # Sequence ownership
        for seq in sequences:
            if seq.owned_by:
                edges.append(
                    Relationship(source=f"{seq.schema}.{seq.name}",
                                 target=seq.owned_by, type="sequence",
                                 label="owned by")
                )

        # View dependencies (catalog-driven)
        try:
            for r in self.db.query(_VIEW_DEPS, {"schemas": self.schemas}):
                edges.append(
                    Relationship(source=r["view"], target=r["source"],
                                 type="view_dependency", label="reads")
                )
        except Exception as exc:  # pragma: no cover - defensive
            self.report.record_warning(f"Could not extract view dependencies: {exc}")

        self.report.record_extracted("relationships", len(edges))
        return edges
