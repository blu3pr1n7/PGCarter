"""Index analysis: duplicates, missing FK indexes, and unused indexes.

Duplicate and missing-FK-index detection are structural and run offline.
Unused-index detection needs runtime counters (``pg_stat_user_indexes``) and so
only produces findings online.
"""

from __future__ import annotations

from sql_dump.analyzer.models import INFO, WARNING, CheckResult
from sql_dump.analyzer.queries import quote_literal
from sql_dump.analyzer.rules import AnalysisContext, DatabaseCheck, constraint_columns, register
from sql_dump.models import Inventory


def _index_signature(columns: list[str], is_unique: bool) -> tuple[str, ...]:
    return (("unique:" if is_unique else "plain:") + ",".join(columns),)


@register
class DuplicateIndexCheck(DatabaseCheck):
    """Flag indexes on the same table covering the same ordered column list."""

    name = "duplicate_indexes"
    category = "index"

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        by_table: dict[str, list] = {}
        for idx in asset.indexes:
            by_table.setdefault(f"{idx.schema}.{idx.table}", []).append(idx)

        for table_name, idxs in by_table.items():
            seen: dict[tuple[str, ...], str] = {}
            for idx in idxs:
                if not idx.columns:
                    continue  # expression indexes: skip signature comparison
                sig = _index_signature(idx.columns, idx.is_unique)
                if sig in seen:
                    results.append(
                        self.result(
                            severity=WARNING,
                            message=(
                                f"Index '{idx.name}' duplicates '{seen[sig]}' "
                                f"on ({', '.join(idx.columns)})"
                            ),
                            table=table_name,
                            details={
                                "index": idx.name,
                                "duplicate_of": seen[sig],
                                "columns": idx.columns,
                            },
                        )
                    )
                else:
                    seen[sig] = idx.name
        return results


@register
class MissingForeignKeyIndexCheck(DatabaseCheck):
    """Flag foreign keys whose referencing columns lack a covering index."""

    name = "missing_fk_indexes"
    category = "index"

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        for table in asset.tables:
            indexes = ctx.indexes_for(table)
            for fk in ctx.foreign_keys(table):
                cols = constraint_columns(fk)
                if not cols:
                    continue
                covered = any(
                    idx.columns[: len(cols)] == cols for idx in indexes if idx.columns
                )
                if not covered:
                    results.append(
                        self.result(
                            severity=WARNING,
                            message=(
                                f"Foreign key '{fk.name}' on ({', '.join(cols)}) "
                                "has no covering index"
                            ),
                            table=table.qualified_name,
                            details={"constraint": fk.name, "columns": cols},
                        )
                    )
        return results


@register
class UnusedIndexCheck(DatabaseCheck):
    """Report never-scanned, non-constraint indexes (online only)."""

    name = "unused_indexes"
    category = "index"
    online_only = True

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        schemas = sorted({t.schema for t in asset.tables})
        array_literal = "ARRAY[" + ", ".join(quote_literal(s) for s in schemas) + "]::text[]"
        sql = (
            "SELECT schemaname AS schema, relname AS table, indexrelname AS index, "
            "idx_scan AS scans\n"
            "FROM pg_catalog.pg_stat_user_indexes\n"
            f"WHERE schemaname = ANY({array_literal}) AND idx_scan = 0\n"
            "ORDER BY schemaname, relname, indexrelname"
        )
        rows = ctx.run(sql)
        if rows is None:
            return [
                self.result(
                    severity=INFO,
                    message="Unused-index detection requires online mode",
                    query=sql,
                    executed=False,
                )
            ]
        constraint_index_names = {i.name for i in asset.indexes if i.is_constraint}
        results: list[CheckResult] = []
        for r in rows:
            index_name = r.get("index")
            if index_name in constraint_index_names:
                continue  # constraint-backing indexes are not "unused"
            results.append(
                self.result(
                    severity=WARNING,
                    message=f"Index '{index_name}' has never been scanned",
                    table=f"{r.get('schema')}.{r.get('table')}",
                    details={"index": index_name, "scans": 0},
                    query=sql,
                    executed=True,
                )
            )
        return results
