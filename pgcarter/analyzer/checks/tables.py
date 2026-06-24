"""Structural and growth-oriented table-level checks.

These complement the size/row-count measurements in
:mod:`pgcarter.analyzer.checks.statistics`. Growth detection keys off
timestamp columns (``created_at``/``updated_at``/…); structural checks (missing
primary key, very wide tables) are derived purely from metadata and so produce
findings even offline.
"""

from __future__ import annotations

from pgcarter.analyzer import heuristics
from pgcarter.analyzer.models import INFO, WARNING, CheckResult
from pgcarter.analyzer.queries import freshness_sql
from pgcarter.analyzer.rules import AnalysisContext, TableCheck, register
from pgcarter.models import Table

# Column names whose min/max bound a table's time span.
_GROWTH_NAMES = ("created_at", "created", "inserted_at", "modified_at", "updated_at")


@register
class GrowthIndicatorCheck(TableCheck):
    """Report the time span covered by a table's freshness timestamp column."""

    name = "growth_indicators"
    category = "table"
    online_only = True

    def _growth_column(self, table: Table) -> str | None:
        names = {c.name.lower() for c in table.columns}
        for candidate in _GROWTH_NAMES:
            if candidate in names:
                return candidate
        # Fall back to any freshness-style timestamp column.
        for c in table.columns:
            if heuristics.is_freshness_name(c.name) and heuristics.is_temporal(c.data_type):
                return c.name
        return None

    def applies(self, asset: Table, ctx: AnalysisContext) -> bool:
        return self._growth_column(asset) is not None

    def execute(self, asset: Table, ctx: AnalysisContext) -> list[CheckResult]:
        column = self._growth_column(asset)
        assert column is not None
        sql = freshness_sql(ctx.relation_expr(asset), column)
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message=f"Growth window available via '{column}' (online)",
                    table=asset.qualified_name,
                    column=column,
                    details={"growth_column": column},
                    query=sql,
                    executed=False,
                )
            ]
        return [
            self.result(
                severity=INFO,
                message=f"Rows span {row.get('earliest')} → {row.get('latest')}",
                table=asset.qualified_name,
                column=column,
                details={
                    "growth_column": column,
                    "earliest": row.get("earliest"),
                    "latest": row.get("latest"),
                },
                query=sql,
                executed=True,
            )
        ]


@register
class TableStructureCheck(TableCheck):
    """Offline structural observations: missing primary key, very wide tables."""

    name = "table_structure"
    category = "table"

    def execute(self, asset: Table, ctx: AnalysisContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        column_count = len(asset.columns)
        results.append(
            self.result(
                severity=INFO,
                message=f"{column_count} columns",
                table=asset.qualified_name,
                details={"column_count": column_count},
            )
        )
        if ctx.primary_key(asset) is None:
            results.append(
                self.result(
                    severity=WARNING,
                    message="Table has no primary key",
                    table=asset.qualified_name,
                    details={"column_count": column_count},
                )
            )
        if column_count >= 40:
            results.append(
                self.result(
                    severity=WARNING,
                    message=f"Very wide table ({column_count} columns)",
                    table=asset.qualified_name,
                    details={"column_count": column_count},
                )
            )
        return results
