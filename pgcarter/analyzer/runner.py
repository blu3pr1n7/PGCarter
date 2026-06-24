"""Orchestration for the ``analyze`` command, decoupled from the CLI framework.

Two modes:

* **Offline** — ``input_dir`` analyzes an existing JSON inventory with no
  database access.
* **Online** — ``database`` connects, builds an inventory by extraction
  (unless ``input_dir`` is also given), and enriches it with profiling queries.
"""

from __future__ import annotations

from pathlib import Path

from pgcarter.analyzer.config import load_analysis_config
from pgcarter.analyzer.engine import AnalysisEngine
from pgcarter.analyzer.loader import load_inventory
from pgcarter.analyzer.models import AnalysisReport
from pgcarter.analyzer.writer import write_analysis
from pgcarter.config import resolve_config
from pgcarter.extractor import Database, InventoryExtractor
from pgcarter.logging_config import get_logger
from pgcarter.report import Report

log = get_logger("pgcarter.analyzer.runner")


class AnalysisInputError(ValueError):
    """Raised when neither an input inventory nor a database was provided."""


def run_analysis(
    *,
    report: Report,
    input_dir: str | None = None,
    host: str = "localhost",
    port: int = 5432,
    database: str | None = None,
    user: str = "postgres",
    password: str | None = None,
    schemas: list[str] | None = None,
    output: str = "./analysis",
    templates_dir: str = "./templates",
    config_path: str | None = None,
    sample_size: int | None = None,
    statement_timeout: int = 0,
) -> AnalysisReport:
    """Run a full analysis and write its outputs, returning the report.

    The supplied :class:`Report` accumulates skips/errors and is the caller's
    handle for deriving an exit code.
    """
    config = load_analysis_config(config_path, sample_size=sample_size)
    resolved_schemas = schemas or ["public"]
    output_dir = Path(output)
    docs_dir = output_dir / "docs" / "analysis"
    templates_path = Path(templates_dir)

    if database:
        # Online: extract a fresh inventory, then keep the connection for profiling.
        conn_config = resolve_config(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            output_dir=output,
            templates_dir=templates_dir,
            schemas=resolved_schemas,
        )
        with Database.connect(conn_config) as db:
            if statement_timeout and statement_timeout > 0:
                # Bound each profiling query; an overrun is logged and skipped.
                db.execute(f"SET statement_timeout = {int(statement_timeout)}")
                log.info("Per-query statement_timeout set to %d ms", statement_timeout)
            if input_dir:
                inventory = load_inventory(input_dir)
            else:
                inventory = InventoryExtractor(db, resolved_schemas, report).extract()
            report.database = inventory.database.name
            analysis = AnalysisEngine(inventory, config, db=db, report=report).analyze()
    else:
        if not input_dir:
            raise AnalysisInputError(
                "provide --input (offline) or --database (online)"
            )
        inventory = load_inventory(input_dir)
        report.database = inventory.database.name
        analysis = AnalysisEngine(inventory, config, db=None, report=report).analyze()

    write_analysis(
        analysis,
        analysis_dir=output_dir,
        docs_dir=docs_dir,
        templates_dir=templates_path,
        report=report,
    )
    return analysis
