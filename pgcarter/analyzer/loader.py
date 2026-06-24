"""Reconstruct an :class:`Inventory` from a JSON inventory directory.

This is the analyzer's primary (offline) input source: the very JSON the
extractor writes via :class:`pgcarter.writers.json_writer.JsonWriter`. Each
dataclass field is populated only from keys it declares, so forward/backward
schema drift (extra or missing keys) degrades gracefully rather than crashing.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from pgcarter.models import (
    Column,
    Constraint,
    DatabaseInfo,
    Grant,
    Index,
    Inventory,
    Relationship,
    Schema,
    Table,
)


class InventoryLoadError(RuntimeError):
    """Raised when the JSON inventory directory cannot be read."""


def _build[T](cls: type[T], data: dict[str, Any]) -> T:
    """Instantiate a dataclass from a dict, ignoring unknown keys."""
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: v for k, v in data.items() if k in known})  # type: ignore[call-arg]


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _table(data: dict[str, Any]) -> Table:
    table = _build(Table, data)
    table.columns = [_build(Column, c) for c in data.get("columns", [])]
    table.constraints = [_build(Constraint, c) for c in data.get("constraints", [])]
    table.grants = [_build(Grant, g) for g in data.get("grants", [])]
    return table


def load_inventory(input_dir: str | Path) -> Inventory:
    """Load an :class:`Inventory` from ``<input_dir>`` (a JSON output directory).

    ``input_dir`` may point at either the inventory root (containing ``json/``)
    or directly at the ``json/`` directory.
    """
    root = Path(input_dir)
    json_dir = root if (root / "tables.json").is_file() else root / "json"
    if not (json_dir / "tables.json").is_file():
        raise InventoryLoadError(
            f"No JSON inventory found under '{input_dir}' "
            "(expected tables.json in the directory or its json/ subdirectory)"
        )

    db_data = _read_json(json_dir / "database.json") or {}
    database = _build(
        DatabaseInfo,
        db_data
        or {
            "name": root.name,
            "version": "",
            "encoding": "",
            "collation": "",
            "ctype": "",
            "owner": "",
        },
    )

    tables = [_table(t) for t in (_read_json(json_dir / "tables.json") or [])]
    schemas = [_build(Schema, s) for s in (_read_json(json_dir / "schemas.json") or [])]
    indexes = [_build(Index, i) for i in (_read_json(json_dir / "indexes.json") or [])]
    relationships = [
        _build(Relationship, r) for r in (_read_json(json_dir / "relationships.json") or [])
    ]
    grants = [_build(Grant, g) for g in (_read_json(json_dir / "permissions.json") or [])]

    if not schemas:
        # Derive schema list from the tables when schemas.json is absent.
        schemas = [Schema(name=name, owner="") for name in sorted({t.schema for t in tables})]

    return Inventory(
        database=database,
        schemas=schemas,
        tables=tables,
        indexes=indexes,
        relationships=relationships,
        grants=grants,
    )
