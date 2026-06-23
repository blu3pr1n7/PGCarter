"""Table, column, and constraint extraction.

Queries are batched across all in-scope schemas (one round trip per asset
category) so the tool scales to databases with hundreds of tables.
"""

from __future__ import annotations

from collections import defaultdict

from ..models import Column, Constraint, Table
from .base import Extractor

_TABLES = """
SELECT
    n.nspname                              AS schema,
    c.relname                              AS name,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    CASE c.relkind WHEN 'p' THEN 'partitioned table' ELSE 'table' END AS kind,
    pg_catalog.obj_description(c.oid, 'pg_class') AS comment,
    c.oid                                  AS oid
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname = ANY(%(schemas)s)
ORDER BY n.nspname, c.relname
"""

_COLUMNS = """
SELECT
    c.oid                                       AS table_oid,
    a.attname                                   AS name,
    a.attnum                                    AS position,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    NOT a.attnotnull                            AS nullable,
    pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) AS default,
    a.attidentity                               AS identity,
    a.attgenerated                              AS generated,
    pg_catalog.col_description(c.oid, a.attnum) AS comment
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
LEFT JOIN pg_catalog.pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum
WHERE c.relkind IN ('r', 'p')
  AND n.nspname = ANY(%(schemas)s)
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.oid, a.attnum
"""

_CONSTRAINTS = """
SELECT
    con.conrelid                              AS table_oid,
    con.conname                               AS name,
    n.nspname                                 AS schema,
    rel.relname                               AS table,
    con.contype                               AS type,
    pg_catalog.pg_get_constraintdef(con.oid, true) AS definition,
    refn.nspname                              AS referenced_schema,
    refc.relname                              AS referenced_table
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = rel.relnamespace
LEFT JOIN pg_catalog.pg_class refc ON refc.oid = con.confrelid
LEFT JOIN pg_catalog.pg_namespace refn ON refn.oid = refc.relnamespace
WHERE n.nspname = ANY(%(schemas)s)
ORDER BY con.conrelid, con.contype, con.conname
"""

_CONTYPE = {
    "p": "PRIMARY KEY",
    "f": "FOREIGN KEY",
    "u": "UNIQUE",
    "c": "CHECK",
    "x": "EXCLUDE",
}
_IDENTITY = {"a": "ALWAYS", "d": "BY DEFAULT"}


class TableExtractor(Extractor):
    name = "table"

    def extract(self) -> list[Table]:
        params = {"schemas": self.schemas}
        table_rows = self.db.query(_TABLES, params)
        columns_by_oid = self._columns(params)
        constraints_by_oid = self._constraints(params)

        tables: list[Table] = []
        for r in table_rows:
            oid = r["oid"]
            tables.append(
                Table(
                    schema=r["schema"],
                    name=r["name"],
                    owner=r["owner"],
                    kind=r["kind"],
                    comment=r["comment"],
                    columns=columns_by_oid.get(oid, []),
                    constraints=constraints_by_oid.get(oid, []),
                )
            )
        self.report.record_extracted("tables", len(tables))
        self.report.record_extracted(
            "constraints", sum(len(t.constraints) for t in tables)
        )
        return tables

    def _columns(self, params: dict) -> dict[int, list[Column]]:
        grouped: dict[int, list[Column]] = defaultdict(list)
        for r in self.db.query(_COLUMNS, params):
            grouped[r["table_oid"]].append(
                Column(
                    name=r["name"],
                    position=r["position"],
                    data_type=r["data_type"],
                    nullable=r["nullable"],
                    default=r["default"],
                    is_identity=bool(r["identity"]),
                    identity_generation=_IDENTITY.get(r["identity"]),
                    is_generated=r["generated"] == "s",
                    generation_expression=r["default"] if r["generated"] == "s" else None,
                    comment=r["comment"],
                )
            )
        return grouped

    def _constraints(self, params: dict) -> dict[int, list[Constraint]]:
        grouped: dict[int, list[Constraint]] = defaultdict(list)
        for r in self.db.query(_CONSTRAINTS, params):
            grouped[r["table_oid"]].append(
                Constraint(
                    name=r["name"],
                    schema=r["schema"],
                    table=r["table"],
                    type=_CONTYPE.get(r["type"], r["type"]),
                    definition=r["definition"],
                    referenced_schema=r["referenced_schema"],
                    referenced_table=r["referenced_table"],
                )
            )
        return grouped
