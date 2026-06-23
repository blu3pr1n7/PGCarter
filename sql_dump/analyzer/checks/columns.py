"""Column-level profiling and name-heuristic checks.

Each check operates on a ``(Table, Column)`` pair. Where a check needs data it
builds a read-only ``SELECT`` (see :mod:`sql_dump.analyzer.queries`) and runs it
through the shared context, which executes online and records-only offline.
Null/cardinality checks share one query string, so the context's result cache
collapses them into a single round trip per column.
"""

from __future__ import annotations

from typing import Any

from ...models import Column, Table
from .. import heuristics
from ..models import CRITICAL, INFO, WARNING, CheckResult
from ..queries import (
    distribution_sql,
    freshness_sql,
    null_and_cardinality_sql,
    string_profile_sql,
    value_distribution_sql,
)
from ..rules import AnalysisContext, ColumnCheck, constraint_columns, register

ColumnAsset = tuple[Table, Column]


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


@register
class NullAnalysisCheck(ColumnCheck):
    """Null percentage for nullable columns; flags high-null / always-null."""

    name = "null_analysis"
    category = "column"
    online_only = True

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return column.nullable

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = null_and_cardinality_sql(ctx.relation_expr(table), column.name)
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Null analysis available online",
                    table=table.qualified_name,
                    column=column.name,
                    query=sql,
                    executed=False,
                )
            ]
        total = int(row.get("total_rows") or 0)
        nulls = int(row.get("null_rows") or 0)
        pct = _pct(nulls, total)
        details = {"null_percentage": pct, "null_rows": nulls, "total_rows": total}
        severity = INFO
        message = f"{pct}% null"
        threshold = ctx.config.thresholds.high_null_percentage
        if total > 0 and nulls == total:
            severity = CRITICAL
            message = "Column is always null"
        elif pct >= threshold:
            severity = WARNING
            message = f"High null rate ({pct}%)"
        return [
            self.result(
                severity=severity,
                message=message,
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class CardinalityCheck(ColumnCheck):
    """Distinct-value count; detects unique identifiers and low-cardinality fields."""

    name = "cardinality"
    category = "column"
    online_only = True

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        # Skip generated columns and large object types where DISTINCT is costly.
        return not column.is_generated and not column.data_type.lower().startswith(
            ("bytea", "json", "xml", "tsvector")
        )

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = null_and_cardinality_sql(ctx.relation_expr(table), column.name)
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Cardinality available online",
                    table=table.qualified_name,
                    column=column.name,
                    query=sql,
                    executed=False,
                )
            ]
        total = int(row.get("total_rows") or 0)
        distinct = int(row.get("distinct_values") or 0)
        ratio = round(distinct / total, 4) if total else 0.0
        details: dict[str, Any] = {
            "distinct_values": distinct,
            "total_rows": total,
            "distinct_ratio": ratio,
        }
        severity = INFO
        message = f"{distinct} distinct values"
        limit = ctx.config.thresholds.low_cardinality_limit
        if total == 0:
            message = "No rows to profile"
        elif ratio >= ctx.config.thresholds.unique_ratio:
            message = f"Effectively unique ({distinct} distinct)"
            details["likely_identifier"] = True
        elif distinct <= limit:
            message = f"Low cardinality ({distinct} distinct)"
            details["low_cardinality"] = True
            if heuristics.is_text(column.data_type):
                details["possible_enum"] = True
                message = f"Low-cardinality text — possible enum ({distinct} distinct)"
        return [
            self.result(
                severity=severity,
                message=message,
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class DistributionCheck(ColumnCheck):
    """min / max / avg for numeric and temporal columns."""

    name = "distribution"
    category = "column"
    online_only = True

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return heuristics.supports_aggregates(column.data_type)

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = distribution_sql(
            ctx.relation_expr(table),
            column.name,
            numeric=heuristics.is_numeric(column.data_type),
        )
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Distribution available online",
                    table=table.qualified_name,
                    column=column.name,
                    query=sql,
                    executed=False,
                )
            ]
        details = {
            "min": row.get("min_value"),
            "max": row.get("max_value"),
            "avg": row.get("avg_value"),
        }
        return [
            self.result(
                severity=INFO,
                message=f"range {row.get('min_value')} … {row.get('max_value')}",
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class StringProfilingCheck(ColumnCheck):
    """Average / minimum / maximum length for text columns."""

    name = "string_profiling"
    category = "column"
    online_only = True

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return heuristics.is_text(column.data_type)

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = string_profile_sql(ctx.relation_expr(table), column.name)
        row = ctx.run_one(sql)
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="String profile available online",
                    table=table.qualified_name,
                    column=column.name,
                    query=sql,
                    executed=False,
                )
            ]
        avg_len = row.get("avg_length")
        details = {
            "avg_length": float(avg_len) if avg_len is not None else None,
            "min_length": row.get("min_length"),
            "max_length": row.get("max_length"),
        }
        severity = INFO
        message = f"avg length {details['avg_length']}"
        if avg_len is not None and float(avg_len) >= ctx.config.thresholds.long_text_length:
            severity = WARNING
            message = f"Very wide text column (avg {round(float(avg_len))} chars)"
        return [
            self.result(
                severity=severity,
                message=message,
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


# --- name-heuristic checks --------------------------------------------------


@register
class IdentifierDetectionCheck(ColumnCheck):
    """For id/uuid-style columns: check indexing offline, uniqueness online."""

    name = "identifier_detection"
    category = "heuristic"

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return heuristics.is_identifier_name(column.name)

    def _is_indexed(self, table: Table, column: Column, ctx: AnalysisContext) -> bool:
        for idx in ctx.indexes_for(table):
            if idx.columns and idx.columns[0] == column.name:
                return True
        pk = ctx.primary_key(table)
        if pk and column.name in constraint_columns(pk):
            return True
        return False

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        indexed = self._is_indexed(table, column, ctx)
        results = [
            self.result(
                severity=INFO,
                message="Identifier-like column",
                table=table.qualified_name,
                column=column.name,
                details={"semantic": "identifier", "indexed": indexed},
            )
        ]
        if not indexed:
            results.append(
                self.result(
                    severity=WARNING,
                    message="Identifier-like column is not indexed",
                    table=table.qualified_name,
                    column=column.name,
                    details={"semantic": "identifier", "indexed": False},
                )
            )
        return results


@register
class TimestampDetectionCheck(ColumnCheck):
    """For timestamp-named columns, run a freshness (min/max) check online."""

    name = "timestamp_detection"
    category = "heuristic"

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return heuristics.is_timestamp_name(column.name) and heuristics.is_temporal(
            column.data_type
        )

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = freshness_sql(ctx.relation_expr(table), column.name)
        row = ctx.run_one(sql)
        details: dict[str, Any] = {"semantic": "timestamp"}
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Freshness check available online",
                    table=table.qualified_name,
                    column=column.name,
                    details=details,
                    query=sql,
                    executed=False,
                )
            ]
        details.update({"earliest": row.get("earliest"), "latest": row.get("latest")})
        return [
            self.result(
                severity=INFO,
                message=f"freshness {row.get('earliest')} … {row.get('latest')}",
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class EmailDetectionCheck(ColumnCheck):
    """For email columns: null rate and duplicate rate."""

    name = "email_detection"
    category = "heuristic"

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return heuristics.is_email_name(column.name) and heuristics.is_text(column.data_type)

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = null_and_cardinality_sql(ctx.relation_expr(table), column.name)
        row = ctx.run_one(sql)
        details: dict[str, Any] = {"semantic": "email"}
        if row is None:
            return [
                self.result(
                    severity=INFO,
                    message="Email null/duplicate check available online",
                    table=table.qualified_name,
                    column=column.name,
                    details=details,
                    query=sql,
                    executed=False,
                )
            ]
        total = int(row.get("total_rows") or 0)
        nulls = int(row.get("null_rows") or 0)
        distinct = int(row.get("distinct_values") or 0)
        non_null = total - nulls
        dup_rate = _pct(non_null - distinct, non_null) if non_null else 0.0
        details.update(
            {
                "null_percentage": _pct(nulls, total),
                "duplicate_rate": dup_rate,
                "distinct_values": distinct,
            }
        )
        severity = WARNING if dup_rate > 0 else INFO
        message = (
            f"Duplicate emails present ({dup_rate}%)" if dup_rate > 0 else "Emails look unique"
        )
        return [
            self.result(
                severity=severity,
                message=message,
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class StatusColumnCheck(ColumnCheck):
    """For status/state/type/category columns, report the value distribution."""

    name = "status_columns"
    category = "heuristic"

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return heuristics.is_status_name(column.name) and not heuristics.is_identifier_name(
            column.name
        )

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = value_distribution_sql(ctx.relation_expr(table), column.name)
        rows = ctx.run(sql)
        details: dict[str, Any] = {"semantic": "status"}
        if rows is None:
            return [
                self.result(
                    severity=INFO,
                    message="Value distribution available online",
                    table=table.qualified_name,
                    column=column.name,
                    details=details,
                    query=sql,
                    executed=False,
                )
            ]
        distribution = {str(r.get("value")): int(r.get("frequency") or 0) for r in rows}
        details["distribution"] = distribution
        return [
            self.result(
                severity=INFO,
                message=f"{len(distribution)} distinct status values",
                table=table.qualified_name,
                column=column.name,
                details=details,
                query=sql,
                executed=True,
            )
        ]


@register
class SuspiciousColumnCheck(ColumnCheck):
    """Single-distinct-value columns: redundant data worth questioning."""

    name = "suspicious_columns"
    category = "quality"
    online_only = True

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        _table, column = asset
        return not column.is_generated and not column.data_type.lower().startswith(
            ("bytea", "json", "xml", "tsvector")
        )

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        table, column = asset
        sql = null_and_cardinality_sql(ctx.relation_expr(table), column.name)
        row = ctx.run_one(sql)
        if row is None:
            return []  # nothing to assert offline; other checks record the query
        total = int(row.get("total_rows") or 0)
        nulls = int(row.get("null_rows") or 0)
        distinct = int(row.get("distinct_values") or 0)
        if total > 0 and nulls < total and distinct == 1:
            return [
                self.result(
                    severity=WARNING,
                    message="Column holds a single distinct value (redundant?)",
                    table=table.qualified_name,
                    column=column.name,
                    details={"distinct_values": 1, "total_rows": total},
                    query=sql,
                    executed=True,
                )
            ]
        return []
