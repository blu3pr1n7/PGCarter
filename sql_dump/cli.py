"""Command-line interface for sql-dump (Typer).

Two subcommands:

* ``index``   — connect to PostgreSQL and produce the schema inventory:
  executable SQL, JSON metadata, and template-driven documentation.
* ``analyze`` — database shape analysis & profiling, offline (from a JSON
  inventory) or online (connecting for statistics).

Exit codes (per subcommand): ``0`` success, ``2`` completed with recorded
errors, ``1`` fatal error.
"""

import os
from enum import StrEnum
from pathlib import Path

import typer

from sql_dump.analyzer.runner import AnalysisInputError, run_analysis
from sql_dump.config import resolve_config
from sql_dump.logging_config import _env_bool, configure_logging, get_logger
from sql_dump.main import run
from sql_dump.report import Report

log = get_logger(__name__)


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _default_level() -> LogLevel:
    """CLI default log level, honouring the LOG_LEVEL environment variable."""
    try:
        return LogLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    except ValueError:
        return LogLevel.INFO


# Env-driven CLI defaults (a flag still overrides them).
_DEFAULT_LEVEL = _default_level()
_DEFAULT_PRETTY = _env_bool("LOG_PRETTY", False)


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "PostgreSQL schema inventory, SQL extraction, documentation, and "
        "database shape analysis. Extracts schema/metadata only — never table "
        "data."
    ),
)


@app.command()
def index(
    database: str = typer.Option(..., "--database", help="Database name to inventory"),
    host: str = typer.Option("localhost", "--host", help="Database host"),
    port: int = typer.Option(5432, "--port", help="Database port"),
    user: str = typer.Option("postgres", "--user", help="Database user"),
    password: str | None = typer.Option(
        None, "--password", help="Database password (falls back to PGPASSWORD)"
    ),
    output_dir: str | None = typer.Option(
        None, "--output-dir", help="Output directory (default: the database name)"
    ),
    templates_dir: str | None = typer.Option(
        None, "--templates-dir", help="Jinja2 templates directory (default: ./templates)"
    ),
    schemas: list[str] | None = typer.Option(
        None, "--schema", help="Schema to extract (repeatable; default: public)"
    ),
    log_level: LogLevel = typer.Option(_DEFAULT_LEVEL, "--log-level", help="Logging verbosity"),
    pretty: bool = typer.Option(
        _DEFAULT_PRETTY,
        "--pretty/--no-pretty",
        help="Colourised developer console logs (default: JSON; or set LOG_PRETTY)",
    ),
) -> None:
    """Extract a PostgreSQL schema inventory (SQL + JSON + docs)."""
    configure_logging(pretty_logs=pretty, level=log_level.value)

    config = resolve_config(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        output_dir=output_dir,
        templates_dir=templates_dir,
        schemas=schemas,
        log_level=log_level.value,
    )

    try:
        report = run(config)
    except Exception as exc:  # noqa: BLE001 - top-level guard
        log.error("sql-dump index failed: %s", exc)
        log.debug("Traceback:", exc_info=True)
        raise typer.Exit(1) from exc

    # A run that produced errors still writes a report, but signals non-zero.
    raise typer.Exit(2 if report.errors else 0)


@app.command()
def analyze(
    input_dir: str | None = typer.Option(
        None, "--input", help="JSON inventory directory to analyze offline (no DB)"
    ),
    host: str = typer.Option("localhost", "--host", help="Database host"),
    port: int = typer.Option(5432, "--port", help="Database port"),
    database: str | None = typer.Option(
        None, "--database", help="Database to connect to for online profiling"
    ),
    user: str = typer.Option("postgres", "--user", help="Database user"),
    password: str | None = typer.Option(
        None, "--password", help="Database password (falls back to PGPASSWORD)"
    ),
    schemas: list[str] | None = typer.Option(
        None, "--schema", help="Schema to analyze (repeatable; default: public)"
    ),
    output: str = typer.Option("./analysis", "--output", help="Output directory"),
    templates_dir: str = typer.Option(
        "./templates", "--templates-dir", help="Jinja2 templates directory"
    ),
    config_path: str | None = typer.Option(
        None, "--config", help="Analysis configuration YAML (enabled_checks, thresholds)"
    ),
    sample_size: int | None = typer.Option(
        None, "--sample-size", help="Row cap for expensive per-column scans"
    ),
    statement_timeout: int = typer.Option(
        0,
        "--statement-timeout",
        help="Per-query timeout in ms for online profiling (0 = none); "
        "an overrun is logged and skipped",
    ),
    log_level: LogLevel = typer.Option(_DEFAULT_LEVEL, "--log-level", help="Logging verbosity"),
    pretty: bool = typer.Option(
        _DEFAULT_PRETTY,
        "--pretty/--no-pretty",
        help="Colourised developer console logs (default: JSON; or set LOG_PRETTY)",
    ),
) -> None:
    """Analyze a database's shape: structure offline, statistics online."""
    configure_logging(pretty_logs=pretty, level=log_level.value)
    report = Report()

    try:
        analysis = run_analysis(
            report=report,
            input_dir=input_dir,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            schemas=schemas,
            output=output,
            templates_dir=templates_dir,
            config_path=config_path,
            sample_size=sample_size,
            statement_timeout=statement_timeout,
        )
    except AnalysisInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - top-level guard
        log.error("sql-dump analyze failed: %s", exc)
        log.debug("Traceback:", exc_info=True)
        raise typer.Exit(1) from exc

    report.finish()
    report.write(Path(output) / "run-report.json")
    log.info(
        "Analysis complete (%s mode): %d tables, %d warnings (%d critical)",
        analysis.mode,
        len(analysis.tables),
        len(analysis.warnings),
        analysis.summary.get("critical_count", 0),
    )
    raise typer.Exit(2 if report.errors else 0)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``sql-dump`` console script."""
    app(args=argv)


if __name__ == "__main__":
    main()
