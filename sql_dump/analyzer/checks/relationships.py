"""Relationship checks over the foreign-key graph.

Reference fan-in ("importance") and relationship depth are computed from the
extracted constraint metadata and run offline. Orphan detection (rows whose
foreign key points at a missing parent) needs data and runs online.
"""

from __future__ import annotations

from ...models import Constraint, Inventory, Table
from ...sql.base import qualified, quote_ident
from ..models import CRITICAL, INFO, WARNING, CheckResult
from ..queries import assert_safe, quote_literal, render_template
from ..rules import AnalysisContext, DatabaseCheck, constraint_columns, register


@register
class HeavilyReferencedCheck(DatabaseCheck):
    """Rank tables by inbound foreign-key count (parent importance / fan-in).

    Online, the authoritative counts come from ``relationships.sql``
    (pg_constraint); offline they are derived from the extracted FK metadata.
    """

    name = "heavily_referenced"
    category = "relationship"

    def _online_counts(self, asset: Inventory, ctx: AnalysisContext) -> dict[str, int] | None:
        schemas = sorted({t.schema for t in asset.tables})
        array_literal = (
            "ARRAY[" + ", ".join(quote_literal(s) for s in schemas) + "]::text[]"
        )
        sql = render_template("relationships.sql", schemas_literal=array_literal)
        rows = ctx.run(sql)
        if rows is None:
            return None
        return {
            f"{r.get('referenced_schema')}.{r.get('referenced_table')}": int(
                r.get("referenced_by") or 0
            )
            for r in rows
        }

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        counts = self._online_counts(asset, ctx) or ctx.referenced_by_counts()
        results: list[CheckResult] = []
        for table, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            severity = WARNING if count >= 10 else INFO
            results.append(
                self.result(
                    severity=severity,
                    message=f"Referenced by {count} foreign key(s)",
                    table=table,
                    details={"referenced_by": count},
                )
            )
        return results


@register
class RelationshipDepthCheck(DatabaseCheck):
    """Report the deepest foreign-key chain reachable from each table."""

    name = "relationship_depth"
    category = "relationship"

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        # Build parent edges: table -> set(referenced tables).
        edges: dict[str, set[str]] = {}
        for table in asset.tables:
            targets: set[str] = set()
            for fk in ctx.foreign_keys(table):
                rs = fk.referenced_schema or table.schema
                if fk.referenced_table:
                    targets.add(f"{rs}.{fk.referenced_table}")
            edges[table.qualified_name] = targets

        def depth(node: str, stack: frozenset[str]) -> int:
            if node in stack:
                return 0  # cycle guard
            best = 0
            for parent in edges.get(node, ()):  # noqa: SIM118
                best = max(best, 1 + depth(parent, stack | {node}))
            return best

        results: list[CheckResult] = []
        for table in asset.tables:
            d = depth(table.qualified_name, frozenset())
            if d > 0:
                results.append(
                    self.result(
                        severity=WARNING if d >= 5 else INFO,
                        message=f"Foreign-key chain depth {d}",
                        table=table.qualified_name,
                        details={"relationship_depth": d},
                    )
                )
        return results


@register
class OrphanRelationshipCheck(DatabaseCheck):
    """Count rows whose foreign key references a non-existent parent (online)."""

    name = "orphan_relationships"
    category = "relationship"
    online_only = True

    def _orphan_sql(
        self, table: Table, fk: Constraint, ctx: AnalysisContext
    ) -> str | None:
        child_cols = constraint_columns(fk)
        parent_cols = list(fk.referenced_columns)
        if not child_cols or not fk.referenced_table:
            return None
        if not parent_cols:
            parent_cols = ["id"]  # conventional default when metadata omits it
        if len(child_cols) != len(parent_cols):
            return None
        rs = fk.referenced_schema or table.schema
        child = qualified(table.schema, table.name)
        parent = qualified(rs, fk.referenced_table)
        join = " AND ".join(
            f"p.{quote_ident(pc)} = c.{quote_ident(cc)}"
            for cc, pc in zip(child_cols, parent_cols, strict=True)
        )
        not_null = " AND ".join(f"c.{quote_ident(cc)} IS NOT NULL" for cc in child_cols)
        sql = (
            "SELECT count(*) AS orphans\n"
            f"FROM {child} c\n"
            f"WHERE {not_null}\n"
            f"  AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE {join})"
        )
        return assert_safe(sql)

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        for table in asset.tables:
            for fk in ctx.foreign_keys(table):
                sql = self._orphan_sql(table, fk, ctx)
                if sql is None:
                    continue
                row = ctx.run_one(sql)
                if row is None:
                    results.append(
                        self.result(
                            severity=INFO,
                            message=f"Orphan check for '{fk.name}' available online",
                            table=table.qualified_name,
                            details={"constraint": fk.name},
                            query=sql,
                            executed=False,
                        )
                    )
                    continue
                orphans = int(row.get("orphans") or 0)
                if orphans > 0:
                    results.append(
                        self.result(
                            severity=CRITICAL,
                            message=f"{orphans} orphaned row(s) via '{fk.name}'",
                            table=table.qualified_name,
                            details={"constraint": fk.name, "orphans": orphans},
                            query=sql,
                            executed=True,
                        )
                    )
        return results
