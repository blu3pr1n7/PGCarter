"""CLI for the ``sql-dump analyze`` subcommand.

Two modes:

* **Offline** — ``--input <json-dir>`` analyses an existing JSON inventory with
  no database access.
* **Online** — ``--database <db>`` connects, builds an inventory by extraction
  (unless ``--input`` is also given), and enriches it with profiling queries.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..config import resolve_config
from ..extractor import Database, InventoryExtractor
from ..logging_config import configure_logging, get_logger
from ..report import Report
from .config import load_analysis_config
from .engine import AnalysisEngine
from .loader import load_inventory
from .models import AnalysisReport
from .writer import write_analysis

log = get_logger("sql_dump.analyzer.cli")


def build_analyze_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sql-dump analyze",
        description="Analyse a PostgreSQL database's shape: structure offline "
        "(from a JSON inventory) and profiling statistics online.",
    )
    # Offline source
    parser.add_argument(
        "--input",
        default=None,
        help="JSON inventory directory to analyse offline (no DB connection)",
    )
    # Online source
    parser.add_argument("--host", default="localhost", help="Database host (default: localhost)")
    parser.add_argument("--port", type=int, default=5432, help="Database port (default: 5432)")
    parser.add_argument(
        "--database",
        default=None,
        help="Database to connect to for online profiling",
    )
    parser.add_argument("--user", default="postgres", help="Database user (default: postgres)")
    parser.add_argument(
        "--password",
        default=None,
        help="Database password (falls back to the PGPASSWORD environment variable)",
    )
    parser.add_argument(
        "--schema",
        dest="schemas",
        action="append",
        default=None,
        help="Schema to analyse (repeatable; default: public)",
    )
    # Output / config
    parser.add_argument(
        "--output",
        default="./analysis",
        help="Output directory for the analysis (default: ./analysis)",
    )
    parser.add_argument(
        "--templates-dir",
        default="./templates",
        help="Jinja2 templates directory (default: ./templates)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Analysis configuration YAML (enabled_checks, thresholds)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Row cap for expensive per-column scans (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Emit structured JSON logs instead of human-readable text",
    )
    return parser


def _run_analysis(args: argparse.Namespace, report: Report) -> AnalysisReport:
    config = load_analysis_config(args.config, sample_size=args.sample_size)
    schemas = args.schemas or ["public"]
    output_dir = Path(args.output)
    docs_dir = output_dir / "docs" / "analysis"
    templates_dir = Path(args.templates_dir)

    if args.database:
        # Online: extract a fresh inventory, then keep the connection for profiling.
        conn_config = resolve_config(
            host=args.host,
            port=args.port,
            database=args.database,
            user=args.user,
            password=args.password,
            output_dir=args.output,
            templates_dir=args.templates_dir,
            schemas=schemas,
        )
        with Database.connect(conn_config) as db:
            if args.input:
                inventory = load_inventory(args.input)
            else:
                inventory = InventoryExtractor(db, schemas, report).extract()
            report.database = inventory.database.name
            analysis = AnalysisEngine(inventory, config, db=db, report=report).analyze()
    else:
        if not args.input:
            raise SystemExit("analyze: provide --input (offline) or --database (online)")
        inventory = load_inventory(args.input)
        report.database = inventory.database.name
        analysis = AnalysisEngine(inventory, config, db=None, report=report).analyze()

    write_analysis(
        analysis,
        analysis_dir=output_dir,
        docs_dir=docs_dir,
        templates_dir=templates_dir,
        report=report,
    )
    return analysis


def analyze_main(argv: list[str]) -> int:
    args = build_analyze_parser().parse_args(argv)
    configure_logging(args.log_level, json_format=args.json_logs)
    report = Report()

    try:
        analysis = _run_analysis(args, report)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level guard
        log.error("sql-dump analyze failed: %s", exc)
        log.debug("Traceback:", exc_info=True)
        return 1

    report.finish()
    report.write(Path(args.output) / "run-report.json")
    log.info(
        "Analysis complete (%s mode): %d tables, %d warnings (%d critical)",
        analysis.mode,
        len(analysis.tables),
        len(analysis.warnings),
        analysis.summary.get("critical_count", 0),
    )
    return 2 if report.errors else 0
