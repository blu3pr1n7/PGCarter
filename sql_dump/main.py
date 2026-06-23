"""Application orchestration: connect, extract, generate SQL, render docs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sql_dump.config import Config
from sql_dump.docs import DocumentationRenderer
from sql_dump.extractor import Database, InventoryExtractor
from sql_dump.logging_config import get_logger
from sql_dump.report import Report
from sql_dump.writers import write_outputs

log = get_logger(__name__)


def _validate_output_dir(path: Path) -> None:
    """Ensure the output directory exists and is writable."""
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".sql_dump_write_test"
    try:
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise PermissionError(f"Output directory '{path}' is not writable: {exc}") from exc


def run(config: Config) -> Report:
    """Execute a full extraction + generation run, returning the run report."""
    timestamp = datetime.now(UTC).isoformat()
    report = Report(database=config.database)

    _validate_output_dir(config.output_dir)

    # --- Extraction -------------------------------------------------------
    with Database.connect(config) as db:
        inventory = InventoryExtractor(db, config.schemas, report).extract()

    # --- SQL + JSON generation (template-free) ----------------------------
    log.info("Writing SQL and JSON outputs to %s", config.output_dir)
    write_outputs(
        inventory,
        sql_dir=config.sql_dir,
        json_dir=config.json_dir,
        timestamp=timestamp,
        report=report,
    )

    # --- Documentation generation (template-driven) -----------------------
    if config.templates_dir.is_dir():
        log.info("Rendering documentation from templates in %s", config.templates_dir)
        DocumentationRenderer(
            config.templates_dir, config.docs_dir, timestamp, report
        ).render(inventory)
    else:
        msg = f"Templates directory '{config.templates_dir}' does not exist; skipping docs"
        log.warning(msg)
        report.record_warning(msg)

    report.finish()
    report.write(config.report_path)
    log.info(
        "Done: %s objects extracted, %s files written, %s warnings, %s errors",
        sum(report.extracted.values()),
        len(report.generated_files),
        len(report.warnings),
        len(report.errors),
    )
    return report
