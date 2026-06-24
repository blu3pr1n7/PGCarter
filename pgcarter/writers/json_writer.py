"""JSON metadata output writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pgcarter.models import Inventory
from pgcarter.report import Report


def _write(path: Path, data: Any, report: Report) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str, sort_keys=False))
    report.record_file(path)


class JsonWriter:
    """Writes structured metadata files under ``<output>/json``."""

    def __init__(self, json_dir: Path, report: Report) -> None:
        self.json_dir = json_dir
        self.report = report

    def write(self, inv: Inventory) -> None:
        d = self.json_dir
        _write(d / "database.json", inv.database.to_dict(), self.report)
        _write(d / "schemas.json", [s.to_dict() for s in inv.schemas], self.report)
        _write(d / "tables.json", [t.to_dict() for t in inv.tables], self.report)
        _write(d / "indexes.json", [i.to_dict() for i in inv.indexes], self.report)
        _write(d / "views.json", [v.to_dict() for v in inv.views], self.report)
        _write(d / "functions.json", [f.to_dict() for f in inv.functions], self.report)
        _write(d / "triggers.json", [t.to_dict() for t in inv.triggers], self.report)
        _write(d / "sequences.json", [s.to_dict() for s in inv.sequences], self.report)
        _write(d / "extensions.json", [e.to_dict() for e in inv.extensions], self.report)
        _write(d / "roles.json", [r.to_dict() for r in inv.roles], self.report)
        _write(d / "permissions.json", [g.to_dict() for g in inv.grants], self.report)
        _write(
            d / "relationships.json",
            [r.to_dict() for r in inv.relationships],
            self.report,
        )
        # Per-schema breakout (json/schemas/<schema>.json) for future schema selection.
        schema_dir = d / "schemas"
        for schema in inv.schemas:
            _write(schema_dir / f"{schema.name}.json", schema.to_dict(), self.report)
        # Per-table breakout (json/tables/<table>.json).
        table_dir = d / "tables"
        for table in inv.tables:
            _write(table_dir / f"{table.name}.json", table.to_dict(), self.report)
