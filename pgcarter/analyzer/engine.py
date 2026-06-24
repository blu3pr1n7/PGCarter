"""The analysis engine: run enabled checks and assemble the report.

The engine feeds each asset to the checks whose scope matches it (tables to
table checks, ``(table, column)`` pairs to column checks, the whole inventory to
database checks), then merges results into :class:`TableAnalysis` /
:class:`ColumnAnalysis` objects. Every non-informational result also becomes a
:class:`Warning`. A failure in one check is captured and never aborts the run,
mirroring the extractor's resilience model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pgcarter.analyzer.config import AnalysisConfig
from pgcarter.analyzer.heuristics import detect_semantics
from pgcarter.analyzer.models import (
    INFO,
    AnalysisReport,
    CheckResult,
    ColumnAnalysis,
    TableAnalysis,
    Warning,
    severity_rank,
)
from pgcarter.analyzer.rules import AnalysisContext, Check, instantiate_checks
from pgcarter.extractor.connection import Database
from pgcarter.logging_config import get_logger
from pgcarter.models import Inventory
from pgcarter.report import Report

log = get_logger("pgcarter.analyzer.engine")


class AnalysisEngine:
    """Run all enabled checks against an inventory (optionally a live DB)."""

    def __init__(
        self,
        inventory: Inventory,
        config: AnalysisConfig,
        db: Database | None = None,
        report: Report | None = None,
    ) -> None:
        self.inventory = inventory
        self.config = config
        self.ctx = AnalysisContext(inventory=inventory, config=config, db=db, report=report)
        self.report = report

    # -- check execution with per-check resilience --------------------------
    def _safe_execute(self, check: Check, asset: Any) -> list[CheckResult]:
        try:
            if not check.applies(asset, self.ctx):
                return []
            return check.execute(asset, self.ctx)
        except Exception as exc:  # noqa: BLE001 - resilience is the point
            log.exception("Check '%s' failed", check.name)
            if self.report is not None:
                self.report.record_error(f"check {check.name}: {exc}")
            return []

    def analyze(self) -> AnalysisReport:
        checks = instantiate_checks(self.config)
        table_checks = [c for c in checks if c.scope == "table"]
        column_checks = [c for c in checks if c.scope == "column"]
        database_checks = [c for c in checks if c.scope == "database"]
        log.info(
            "Running %d checks (%d table, %d column, %d database) over %d tables",
            len(checks),
            len(table_checks),
            len(column_checks),
            len(database_checks),
            len(self.inventory.tables),
        )

        analyses: dict[str, TableAnalysis] = {}
        all_results: list[CheckResult] = []

        total_tables = len(self.inventory.tables)
        for index, table in enumerate(self.inventory.tables, start=1):
            queried = (
                f"; {len(self.ctx.generated_queries)} queries so far" if self.ctx.online else ""
            )
            log.info(
                "[%d/%d] analyzing %s (%d columns)%s",
                index,
                total_tables,
                table.qualified_name,
                len(table.columns),
                queried,
            )
            ta = TableAnalysis(schema=table.schema, name=table.name)
            for check in table_checks:
                for r in self._safe_execute(check, table):
                    ta.checks.append(r)
                    _merge(ta.metrics, r.details)
                    all_results.append(r)
            for column in table.columns:
                ca = ColumnAnalysis(
                    name=column.name,
                    data_type=column.data_type,
                    nullable=column.nullable,
                    semantics=detect_semantics(column),
                )
                for check in column_checks:
                    for r in self._safe_execute(check, (table, column)):
                        ca.checks.append(r)
                        _merge_column(ca, r.details)
                        all_results.append(r)
                ta.columns.append(ca)
            analyses[ta.qualified_name] = ta

        # Database-scope checks (relationships, indexes, cross-table quality).
        for index, check in enumerate(database_checks, start=1):
            log.info("[db %d/%d] running %s", index, len(database_checks), check.name)
            for r in self._safe_execute(check, self.inventory):
                all_results.append(r)
                if r.table and r.table in analyses:
                    analyses[r.table].checks.append(r)

        warnings = [
            Warning(
                severity=r.severity,
                category=r.category,
                check=r.check,
                message=r.message,
                table=r.table,
                column=r.column,
                details=r.details,
            )
            for r in all_results
            if r.severity != INFO
        ]
        warnings.sort(key=lambda w: (-severity_rank(w.severity), w.table or "", w.check))

        tables = sorted(analyses.values(), key=lambda t: t.qualified_name)
        report = AnalysisReport(
            database=self.inventory.database.name,
            mode="online" if self.ctx.online else "offline",
            schemas=sorted({t.schema for t in self.inventory.tables}),
            generated_at=datetime.now(UTC).isoformat(),
            sample_size=self.config.sample_size,
            tables=tables,
            warnings=warnings,
        )
        report.summary = _summarise(report, all_results)
        if self.report is not None:
            self.report.record_extracted("checks_run", len(all_results))
            self.report.record_extracted("warnings", len(warnings))
        return report


def _merge(target: dict[str, Any], details: dict[str, Any]) -> None:
    """Merge check details into a metrics dict, ignoring control keys."""
    for k, v in details.items():
        if k == "semantic":
            continue
        target[k] = v


def _merge_column(ca: ColumnAnalysis, details: dict[str, Any]) -> None:
    for k, v in details.items():
        if k == "semantic":
            if v not in ca.semantics:
                ca.semantics.append(str(v))
        else:
            ca.stats[k] = v


def _summarise(report: AnalysisReport, results: list[CheckResult]) -> dict[str, Any]:
    by_severity: dict[str, int] = {}
    for r in results:
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
    return {
        "tables_analyzed": len(report.tables),
        "checks_run": len(results),
        "results_by_severity": by_severity,
        "warning_count": len(report.warnings),
        "critical_count": sum(1 for w in report.warnings if w.severity == "critical"),
    }
