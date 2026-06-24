"""Extraction orchestration.

The :class:`InventoryExtractor` runs each category extractor in turn. A failure
in any single extractor is captured in the report and does not abort the run,
so a database the connecting role can only partially read still yields a
best-effort inventory.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pgcarter.extractor.connection import Database
from pgcarter.extractor.database import DatabaseExtractor
from pgcarter.extractor.extensions import ExtensionExtractor
from pgcarter.extractor.functions import FunctionExtractor
from pgcarter.extractor.indexes import IndexExtractor
from pgcarter.extractor.permissions import PermissionExtractor
from pgcarter.extractor.relationships import RelationshipExtractor
from pgcarter.extractor.roles import RoleExtractor
from pgcarter.extractor.schemas import SchemaExtractor
from pgcarter.extractor.sequences import SequenceExtractor
from pgcarter.extractor.tables import TableExtractor
from pgcarter.extractor.triggers import TriggerExtractor
from pgcarter.extractor.views import ViewExtractor
from pgcarter.logging_config import get_logger
from pgcarter.models import (
    Function,
    Grant,
    Inventory,
    Schema,
    Sequence,
    Table,
    View,
)
from pgcarter.report import Report

log = get_logger(__name__)


class InventoryExtractor:
    def __init__(self, db: Database, schemas: list[str], report: Report) -> None:
        self.db = db
        self.schemas = schemas
        self.report = report

    def _safe(self, label: str, fn: Callable[[], Any], default: Any) -> Any:
        """Run an extraction step, capturing failures into the report."""
        try:
            log.info("Extracting %s", label)
            return fn()
        except Exception as exc:  # noqa: BLE001 - resilience is the point
            log.exception("Failed to extract %s", label)
            self.report.record_error(f"{label}: {exc}")
            return default

    def extract(self) -> Inventory:
        db, schemas, report = self.db, self.schemas, self.report

        database = self._safe(
            "database", lambda: DatabaseExtractor(db, schemas, report).extract(), None
        )
        if database is None:
            raise RuntimeError("Unable to extract core database metadata; aborting")
        self.report.database = database.name

        schemas_list = self._safe(
            "schemas", lambda: SchemaExtractor(db, schemas, report).extract(), []
        )
        tables = self._safe(
            "tables", lambda: TableExtractor(db, schemas, report).extract(), []
        )
        indexes = self._safe(
            "indexes", lambda: IndexExtractor(db, schemas, report).extract(), []
        )
        views = self._safe(
            "views", lambda: ViewExtractor(db, schemas, report).extract(), []
        )
        functions = self._safe(
            "functions", lambda: FunctionExtractor(db, schemas, report).extract(), []
        )
        triggers = self._safe(
            "triggers", lambda: TriggerExtractor(db, schemas, report).extract(), []
        )
        sequences = self._safe(
            "sequences", lambda: SequenceExtractor(db, schemas, report).extract(), []
        )
        extensions = self._safe(
            "extensions", lambda: ExtensionExtractor(db, schemas, report).extract(), []
        )
        roles = self._safe(
            "roles", lambda: RoleExtractor(db, schemas, report).extract(), []
        )
        grants = self._safe(
            "permissions", lambda: PermissionExtractor(db, schemas, report).extract(), []
        )

        # Attach grants back to their owning models for per-object rendering.
        self._attach_grants(grants, schemas_list, tables, views, functions, sequences)

        relationships = self._safe(
            "relationships",
            lambda: RelationshipExtractor(db, schemas, report).build(
                tables, triggers, sequences, functions
            ),
            [],
        )

        return Inventory(
            database=database,
            schemas=schemas_list,
            tables=tables,
            indexes=indexes,
            views=views,
            functions=functions,
            triggers=triggers,
            sequences=sequences,
            extensions=extensions,
            roles=roles,
            grants=grants,
            relationships=relationships,
        )

    @staticmethod
    def _attach_grants(
        grants: list[Grant],
        schemas_list: list[Schema],
        tables: list[Table],
        views: list[View],
        functions: list[Function],
        sequences: list[Sequence],
    ) -> None:
        by_schema = {s.name: s for s in schemas_list}
        by_table = {t.qualified_name: t for t in tables}
        by_view = {f"{v.schema}.{v.name}": v for v in views}
        by_seq = {f"{s.schema}.{s.name}": s for s in sequences}
        by_func = {f"{f.schema}.{f.signature}": f for f in functions}

        for g in grants:
            if g.object_type == "schema" and g.object_name in by_schema:
                by_schema[g.object_name].grants.append(g)
            elif g.object_type == "table":
                if g.object_name in by_table:
                    by_table[g.object_name].grants.append(g)
                elif g.object_name in by_view:
                    by_view[g.object_name].grants.append(g)
            elif g.object_type == "sequence" and g.object_name in by_seq:
                by_seq[g.object_name].grants.append(g)
            elif g.object_type == "function" and g.object_name in by_func:
                by_func[g.object_name].grants.append(g)


__all__ = ["Database", "InventoryExtractor"]
