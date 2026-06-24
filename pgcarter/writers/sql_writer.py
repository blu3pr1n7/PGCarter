"""Executable SQL (DDL) output writer.

Lays out files under ``<output>/sql`` following the documented structure and
wraps every file with the mandatory provenance header.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from pgcarter.models import Inventory
from pgcarter.report import Report
from pgcarter.sql import generators as gen
from pgcarter.sql.base import with_header

_SAFE = re.compile(r"[^A-Za-z0-9_]+")


def _slug(name: str) -> str:
    slug = _SAFE.sub("_", name).strip("_")
    return slug or "object"


class SqlWriter:
    def __init__(self, sql_dir: Path, database: str, timestamp: str, report: Report) -> None:
        self.sql_dir = sql_dir
        self.database = database
        self.timestamp = timestamp
        self.report = report

    def _write(self, path: Path, obj: str, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(with_header(self.database, obj, self.timestamp, body))
        self.report.record_file(path)

    def _schema_dir(self, schema: str, sub: str) -> Path:
        return self.sql_dir / "schemas" / schema / sub

    def _unique(self, used: set[str], base: str) -> str:
        name = base
        n = 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        used.add(name)
        return name

    def write(self, inv: Inventory) -> None:
        self._write(
            self.sql_dir / "database.sql", inv.database.name, gen.database_sql(inv.database)
        )

        if inv.extensions:
            self._write(
                self.sql_dir / "extensions.sql", "extensions", gen.extensions_sql(inv.extensions)
            )
        if inv.roles:
            self._write(self.sql_dir / "roles.sql", "roles", gen.roles_sql(inv.roles))

        for schema in inv.schemas:
            self._write(
                self.sql_dir / "schemas" / f"{schema.name}.sql", schema.name, gen.schema_sql(schema)
            )

        self._write_per_schema(inv)
        self._write_permissions(inv)

    def _write_per_schema(self, inv: Inventory) -> None:
        used: dict[str, set[str]] = defaultdict(set)

        for t in inv.tables:
            base = self._unique(used[f"{t.schema}/tables"], _slug(t.name))
            self._write(
                self._schema_dir(t.schema, "tables") / f"{base}.sql",
                t.qualified_name,
                gen.table_sql(t),
            )

        for i in inv.indexes:
            if i.is_primary or i.is_constraint:
                continue  # created as part of the table's constraints
            base = self._unique(used[f"{i.schema}/indexes"], _slug(i.name))
            self._write(
                self._schema_dir(i.schema, "indexes") / f"{base}.sql",
                f"{i.schema}.{i.name}",
                gen.index_sql(i),
            )

        for v in inv.views:
            base = self._unique(used[f"{v.schema}/views"], _slug(v.name))
            self._write(
                self._schema_dir(v.schema, "views") / f"{base}.sql",
                f"{v.schema}.{v.name}",
                gen.view_sql(v),
            )

        for f in inv.functions:
            base = self._unique(used[f"{f.schema}/functions"], _slug(f.name))
            self._write(
                self._schema_dir(f.schema, "functions") / f"{base}.sql",
                f"{f.schema}.{f.signature}",
                gen.function_sql(f),
            )

        for trg in inv.triggers:
            base = self._unique(used[f"{trg.schema}/triggers"], _slug(trg.name))
            self._write(
                self._schema_dir(trg.schema, "triggers") / f"{base}.sql",
                f"{trg.schema}.{trg.name}",
                gen.trigger_sql(trg),
            )

        for s in inv.sequences:
            if s.is_identity:
                continue  # recreated by the owning table's IDENTITY clause
            base = self._unique(used[f"{s.schema}/sequences"], _slug(s.name))
            self._write(
                self._schema_dir(s.schema, "sequences") / f"{base}.sql",
                f"{s.schema}.{s.name}",
                gen.sequence_sql(s),
            )

    def _write_permissions(self, inv: Inventory) -> None:
        # Group grants by (schema, local object name); database grants go top-level.
        groups: dict[tuple[str | None, str], list] = defaultdict(list)
        for g in inv.grants:
            if g.object_type == "database":
                groups[(None, g.object_name)].append(g)
            elif g.object_type == "schema":
                groups[(g.object_name, "schema")].append(g)
            else:
                schema = g.object_name.split(".", 1)[0]
                local = g.object_name.split(".", 1)[1] if "." in g.object_name else g.object_name
                groups[(schema, local)].append(g)

        ordered = sorted(groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1]))
        for (grp_schema, grp_local), grants in ordered:
            body = gen.permissions_sql(grants)
            if grp_schema is None:
                path = self.sql_dir / "permissions" / f"{_slug(grp_local)}.sql"
                obj = f"permissions:{grp_local}"
            else:
                path = self._schema_dir(grp_schema, "permissions") / f"{_slug(grp_local)}.sql"
                obj = f"permissions:{grp_schema}.{grp_local}"
            self._write(path, obj, body)
