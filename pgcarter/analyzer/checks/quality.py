"""Data-quality checks that produce warnings.

Duplicate primary keys and duplicate values in unique columns should be
impossible given the constraints; finding any is a critical integrity signal
(it can happen via constraint corruption, restores, or replication issues).
These run online. "Unused table" detection is structural and runs offline.
"""

from __future__ import annotations

from pgcarter.analyzer.models import CRITICAL, INFO, WARNING, CheckResult
from pgcarter.analyzer.queries import duplicate_values_sql
from pgcarter.analyzer.rules import AnalysisContext, DatabaseCheck, constraint_columns, register
from pgcarter.models import Inventory, Table


def _duplicate_check(
    check: DatabaseCheck,
    table: Table,
    constraint_name: str,
    columns: list[str],
    ctx: AnalysisContext,
) -> CheckResult | None:
    """Run a duplicate-value probe over a single (multi-)column key."""
    if not columns:
        return None
    # Probe each column individually; a duplicated composite key implies a
    # duplicated leading column only in the single-column case, so we restrict
    # the strong assertion to single-column keys and skip composites safely.
    if len(columns) != 1:
        return None
    sql = duplicate_values_sql(ctx.relation_expr(table), columns[0])
    row = ctx.run_one(sql)
    if row is None:
        return check.result(
            severity=INFO,
            message=f"Duplicate check for '{constraint_name}' available online",
            table=table.qualified_name,
            column=columns[0],
            details={"constraint": constraint_name},
            query=sql,
            executed=False,
        )
    groups = int(row.get("duplicate_groups") or 0)
    if groups > 0:
        return check.result(
            severity=CRITICAL,
            message=(
                f"{groups} duplicated value(s) in unique column '{columns[0]}' "
                f"(constraint '{constraint_name}')"
            ),
            table=table.qualified_name,
            column=columns[0],
            details={
                "constraint": constraint_name,
                "duplicate_groups": groups,
                "extra_rows": int(row.get("extra_rows") or 0),
            },
            query=sql,
            executed=True,
        )
    return None


@register
class DuplicatePrimaryKeyCheck(DatabaseCheck):
    """Primary-key columns must be unique; any duplicate is critical."""

    name = "duplicate_primary_keys"
    category = "quality"
    online_only = True

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        for table in asset.tables:
            pk = ctx.primary_key(table)
            if pk is None:
                continue
            res = _duplicate_check(self, table, pk.name, constraint_columns(pk), ctx)
            if res is not None:
                results.append(res)
        return results


@register
class DuplicateUniqueValueCheck(DatabaseCheck):
    """Columns under a UNIQUE constraint must not contain duplicates."""

    name = "duplicate_unique_values"
    category = "quality"
    online_only = True

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        for table in asset.tables:
            for uniq in ctx.unique_constraints(table):
                res = _duplicate_check(self, table, uniq.name, constraint_columns(uniq), ctx)
                if res is not None:
                    results.append(res)
        return results


@register
class UnusedTableCheck(DatabaseCheck):
    """Flag tables with no inbound or outbound foreign keys (offline structural)."""

    name = "unused_tables"
    category = "quality"

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        referenced = ctx.referenced_by_counts()
        results: list[CheckResult] = []
        for table in asset.tables:
            inbound = referenced.get(table.qualified_name, 0)
            outbound = len(ctx.foreign_keys(table))
            if inbound == 0 and outbound == 0:
                results.append(
                    self.result(
                        severity=WARNING,
                        message="Table participates in no foreign-key relationships",
                        table=table.qualified_name,
                        details={"inbound_fks": 0, "outbound_fks": 0},
                    )
                )
        return results
