"""Command-line interface for sql-dump."""

from __future__ import annotations

import argparse
import sys

from .config import resolve_config
from .logging_config import configure_logging, get_logger
from .main import run

log = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sql-dump",
        description="PostgreSQL schema inventory, SQL extraction, and documentation "
                    "generation tool. Extracts schema/metadata only — never table data. "
                    "Use the 'analyze' subcommand for database shape analysis and profiling.",
    )
    parser.add_argument("--host", default="localhost", help="Database host (default: localhost)")
    parser.add_argument("--port", type=int, default=5432, help="Database port (default: 5432)")
    parser.add_argument("--database", required=True, help="Database name to inventory")
    parser.add_argument("--user", default="postgres", help="Database user (default: postgres)")
    parser.add_argument(
        "--password",
        default=None,
        help="Database password (falls back to the PGPASSWORD environment variable)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: the database name)",
    )
    parser.add_argument(
        "--templates-dir",
        default=None,
        help="Jinja2 templates directory (default: ./templates)",
    )
    parser.add_argument(
        "--schema",
        dest="schemas",
        action="append",
        default=None,
        help="Schema to extract (repeatable; default: public)",
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # ``sql-dump analyze ...`` routes to the analysis subsystem. The default
    # (no subcommand) preserves the original extraction CLI verbatim.
    if argv and argv[0] == "analyze":
        from .analyzer.cli import analyze_main

        return analyze_main(argv[1:])

    args = build_parser().parse_args(argv)
    configure_logging(args.log_level, json_format=args.json_logs)

    config = resolve_config(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
        output_dir=args.output_dir,
        templates_dir=args.templates_dir,
        schemas=args.schemas,
        log_level=args.log_level,
    )

    try:
        report = run(config)
    except Exception as exc:  # noqa: BLE001 - top-level guard
        log.error("sql-dump failed: %s", exc)
        log.debug("Traceback:", exc_info=True)
        return 1

    # A run that produced errors still writes a report, but signals non-zero.
    return 2 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
