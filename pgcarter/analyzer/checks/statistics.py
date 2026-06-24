"""Statistical table-level checks: physical size and estimated row count.

Both draw on ``queries/table_stats.sql`` (one cached round trip per table) and
prefer PostgreSQL's own statistics (``pg_class.reltuples``,
``pg_total_relation_size``) over scanning, so they stay cheap on large
databases.
"""

from __future__ import annotations

from pgcarter.analyzer.models import INFO, WARNING, CheckResult
from pgcarter.analyzer.queries import assert_safe, quote_literal, render_template
from pgcarter.analyzer.rules import AnalysisContext, TableCheck, register
from pgcarter.models import Table


def _table_stats_sql(table: Table) -> str:
    return render_template(
        "table_stats.sql",
        schema_literal=quote_literal(table.schema),
        table_literal=quote_literal(table.name),
        relation_literal=quote_literal(table.qualified_name),
    )


@register
class TableSizeCheck(TableCheck):
    """Capture table, index, and total size for a relation."""

    name = "table_size"
    category = "statistics"
    online_only = True

    def execute(self, asset: Table, ctx: AnalysisContext) -> list[CheckResult]:
        sql = _table_stats_sql(asset)
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Size metrics require online mode",
                    table=asset.qualified_name,
                    query=sql,
                    executed=False,
                )
            ]
        details = {
            "total_bytes": row.get("total_bytes"),
            "table_bytes": row.get("table_bytes"),
            "index_bytes": row.get("index_bytes"),
            "total_size": row.get("total_pretty"),
            "table_size": row.get("table_pretty"),
            "index_size": row.get("index_pretty"),
        }
        return [
            self.result(
                severity=INFO,
                message=f"Total size {row.get('total_pretty')}",
                table=asset.qualified_name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class RowCountCheck(TableCheck):
    """Estimate row count and flag empty or extremely large tables."""

    name = "row_count"
    category = "statistics"
    online_only = True

    def execute(self, asset: Table, ctx: AnalysisContext) -> list[CheckResult]:
        sql = _table_stats_sql(asset)
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Row count estimate requires online mode",
                    table=asset.qualified_name,
                    query=sql,
                    executed=False,
                )
            ]
        estimated = int(row.get("estimated_rows") or 0)
        exact: int | None = None
        # reltuples is -1 when the table has never been ANALYZEd: that means
        # "unknown", not "empty". Fall back to an exact count only in that case,
        # so we never scan a table whose estimate is already trustworthy.
        if estimated < 0:
            count_sql = assert_safe(
                f"SELECT count(*) AS exact FROM {ctx.relation_expr(asset)}"
            )
            count_row = ctx.run_one(count_sql)
            if count_row is not None:
                exact = int(count_row.get("exact") or 0)
                estimated = exact
        rows = exact if exact is not None else estimated
        details = {"estimated_rows": estimated, "exact_rows": exact}
        results = [
            self.result(
                severity=INFO,
                message=f"{'Counted' if exact is not None else 'Estimated'} {rows:,} rows",
                table=asset.qualified_name,
                details=details,
                query=sql,
                executed=True,
            )
        ]
        if rows <= 0:
            results.append(
                self.result(
                    severity=WARNING,
                    message="Table is empty",
                    table=asset.qualified_name,
                    details=details,
                    executed=True,
                )
            )
        elif rows >= ctx.config.thresholds.large_table_rows:
            results.append(
                self.result(
                    severity=WARNING,
                    message=f"Extremely large table (~{rows:,} rows)",
                    table=asset.qualified_name,
                    details=details,
                    executed=True,
                )
            )
        return results
