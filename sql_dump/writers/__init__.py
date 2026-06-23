"""Output writers: SQL files, JSON metadata, and the relationship graph."""

from __future__ import annotations

from pathlib import Path

from sql_dump.models import Inventory
from sql_dump.report import Report
from sql_dump.writers.apply import write_apply
from sql_dump.writers.graph import write_dot
from sql_dump.writers.json_writer import JsonWriter
from sql_dump.writers.sql_writer import SqlWriter

__all__ = ["JsonWriter", "SqlWriter", "write_apply", "write_dot", "write_outputs"]


def write_outputs(
    inv: Inventory,
    *,
    sql_dir: Path,
    json_dir: Path,
    timestamp: str,
    report: Report,
) -> None:
    """Write the SQL and JSON outputs (the template-free deliverables)."""
    SqlWriter(sql_dir, inv.database.name, timestamp, report).write(inv)
    write_apply(sql_dir / "apply.sql", inv, timestamp, report)
    JsonWriter(json_dir, report).write(inv)
    write_dot(json_dir / "relationships.dot", inv.relationships, report)
