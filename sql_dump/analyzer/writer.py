"""Output writers for analysis results.

Two layers, mirroring the extractor's separation of concerns:

* :class:`AnalysisJsonWriter` — template-free structured JSON
  (``report.json``, ``warnings.json``, ``tables/<table>.json``).
* :class:`AnalysisDocRenderer` — Jinja2-rendered Markdown. As with the rest of
  the project, **no Markdown is embedded in Python**; every document comes from
  an external template, and a missing template is warned-and-skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from sql_dump.analyzer.models import AnalysisReport, TableAnalysis
from sql_dump.logging_config import get_logger
from sql_dump.report import Report

log = get_logger("sql_dump.analyzer.writer")


def _write_json(path: Path, data: Any, report: Report | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str, sort_keys=False))
    if report is not None:
        report.record_file(path)


class AnalysisJsonWriter:
    """Writes ``report.json``, ``warnings.json`` and per-table JSON."""

    def __init__(self, output_dir: Path, report: Report | None = None) -> None:
        self.output_dir = output_dir
        self.report = report

    def write(self, analysis: AnalysisReport) -> None:
        d = self.output_dir
        _write_json(d / "report.json", analysis.to_dict(), self.report)
        _write_json(
            d / "warnings.json",
            [w.to_dict() for w in analysis.warnings],
            self.report,
        )
        table_dir = d / "tables"
        for table in analysis.tables:
            _write_json(table_dir / f"{table.name}.json", table.to_dict(), self.report)


class AnalysisDocRenderer:
    """Renders analysis Markdown from an external Jinja2 template directory."""

    def __init__(
        self,
        templates_dir: Path,
        docs_dir: Path,
        analysis_dir: Path,
        report: Report | None = None,
    ) -> None:
        self.templates_dir = templates_dir
        self.docs_dir = docs_dir
        self.analysis_dir = analysis_dir
        self.report = report
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(enabled_extensions=(), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def _has(self, template: str) -> bool:
        if (self.templates_dir / template).is_file():
            return True
        log.warning("Analysis template '%s' not found; skipping", template)
        if self.report is not None:
            self.report.record_warning(f"Analysis template '{template}' not found; skipped")
        return False

    def _render(self, template: str, out: Path, **context: Any) -> None:
        try:
            tmpl = self.env.get_template(template)
        except TemplateNotFound:
            log.warning("Analysis template '%s' disappeared; skipping", template)
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(tmpl.render(**context))
        if self.report is not None:
            self.report.record_file(out)

    def render(self, analysis: AnalysisReport) -> None:
        ctx = {
            "report": analysis.to_dict(),
            "tables": [t.to_dict() for t in analysis.tables],
            "warnings": [w.to_dict() for w in analysis.warnings],
            "generated_at": analysis.generated_at,
        }

        # analysis/report.md — top-level summary (also feeds docs/analysis/index.md)
        if self._has("analysis.md.j2"):
            self._render("analysis.md.j2", self.analysis_dir / "report.md", **ctx)
            self._render("analysis.md.j2", self.docs_dir / "index.md", **ctx)

        if self._has("warnings.md.j2"):
            self._render("warnings.md.j2", self.docs_dir / "warnings.md", **ctx)

        if self._has("table_analysis.md.j2"):
            for table in analysis.tables:
                self._render_table(table)

    def _render_table(self, table: TableAnalysis) -> None:
        self._render(
            "table_analysis.md.j2",
            self.docs_dir / "tables" / f"{table.name}.md",
            table=table.to_dict(),
            generated_at="",
        )


def write_analysis(
    analysis: AnalysisReport,
    *,
    analysis_dir: Path,
    docs_dir: Path,
    templates_dir: Path,
    report: Report | None = None,
) -> None:
    """Write JSON outputs and (if templates exist) Markdown documentation."""
    AnalysisJsonWriter(analysis_dir, report).write(analysis)
    if templates_dir.is_dir():
        AnalysisDocRenderer(templates_dir, docs_dir, analysis_dir, report).render(analysis)
    else:
        msg = f"Templates directory '{templates_dir}' does not exist; skipping analysis docs"
        log.warning(msg)
        if report is not None:
            report.record_warning(msg)
