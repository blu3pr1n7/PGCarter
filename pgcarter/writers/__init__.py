"""Output writers: SQL files, JSON metadata, and the relationship graph."""

from __future__ import annotations

from pathlib import Path

from pgcarter.models import Inventory
from pgcarter.report import Report
from pgcarter.writers.apply import write_apply
from pgcarter.writers.graph import write_dot
from pgcarter.writers.json_writer import JsonWriter
from pgcarter.writers.sql_writer import SqlWriter

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
