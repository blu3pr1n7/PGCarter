"""Extractor unit tests using a fake database (no live PostgreSQL required)."""

from __future__ import annotations

from typing import Any

from pgcarter.extractor.database import DatabaseExtractor
from pgcarter.extractor.indexes import IndexExtractor
from pgcarter.extractor.permissions import PermissionExtractor
from pgcarter.extractor.tables import TableExtractor
from pgcarter.extractor.triggers import _decode
from pgcarter.report import Report


class FakeDB:
    """Returns canned rows based on a marker substring found in each query."""

    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self.responses = responses

    def _match(self, sql: str) -> list[dict[str, Any]]:
        for marker, rows in self.responses.items():
            if marker in sql:
                return rows
        return []

    def query(self, sql, params=None):
        return self._match(sql)

    def query_one(self, sql, params=None):
        rows = self._match(sql)
        return rows[0] if rows else None


def test_database_extractor():
    db = FakeDB({"pg_database": [{
        "name": "shop", "version": "16.2", "encoding": "UTF8",
        "collation": "en_US.UTF-8", "ctype": "en_US.UTF-8",
        "owner": "postgres", "comment": None,
    }]})
    report = Report()
    info = DatabaseExtractor(db, ["public"], report).extract()
    assert info.name == "shop"
    assert info.version == "16.2"
    assert report.extracted["database"] == 1


def test_table_extractor_groups_columns_and_constraints():
    db = FakeDB({
        "FROM pg_catalog.pg_class c\nJOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace\nWHERE c.relkind IN ('r', 'p')\n  AND n.nspname": [
            {"schema": "public", "name": "t", "owner": "o",
             "kind": "table", "comment": None, "oid": 1},
        ],
        "JOIN pg_catalog.pg_attribute a": [
            {"table_oid": 1, "name": "id", "position": 1, "data_type": "integer",
             "nullable": False, "default": None, "identity": "d",
             "generated": "", "comment": None},
            {"table_oid": 1, "name": "label", "position": 2, "data_type": "text",
             "nullable": True, "default": None, "identity": "",
             "generated": "", "comment": None},
        ],
        "pg_get_constraintdef": [
            {"table_oid": 1, "name": "t_pkey", "schema": "public", "table": "t",
             "type": "p", "definition": "PRIMARY KEY (id)",
             "referenced_schema": None, "referenced_table": None},
        ],
    })
    report = Report()
    tables = TableExtractor(db, ["public"], report).extract()
    assert len(tables) == 1
    t = tables[0]
    assert len(t.columns) == 2
    assert t.columns[0].is_identity is True
    assert t.columns[0].identity_generation == "BY DEFAULT"
    assert t.constraints[0].type == "PRIMARY KEY"


def test_index_extractor():
    db = FakeDB({"pg_get_indexdef": [
        {"schema": "public", "name": "i1", "table": "t",
         "definition": "CREATE INDEX i1 ON public.t (x)", "is_unique": False,
         "is_primary": False, "is_constraint": False, "method": "btree",
         "predicate": None, "columns": ["x"], "has_expressions": False},
    ]})
    report = Report()
    idx = IndexExtractor(db, ["public"], report).extract()
    assert idx[0].method == "btree"
    assert idx[0].columns == ["x"]


def test_permission_extractor_classifies_objects():
    db = FakeDB({
        "FROM pg_catalog.pg_database d": [
            {"object_name": "shop", "grantee": "PUBLIC", "privilege": "CONNECT",
             "grantable": False},
        ],
        "FROM pg_catalog.pg_namespace n,": [
            {"object_name": "public", "grantee": "app", "privilege": "USAGE",
             "grantable": False},
        ],
        "FROM pg_catalog.pg_class c\nJOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace,": [
            {"object_name": "public.t", "object_type": "table", "grantee": "ro",
             "privilege": "SELECT", "grantable": False},
        ],
    })
    report = Report()
    grants = PermissionExtractor(db, ["public"], report).extract()
    kinds = {g.object_type for g in grants}
    assert "database" in kinds
    assert "schema" in kinds
    assert "table" in kinds


def test_trigger_bitmask_decode():
    # BEFORE INSERT OR UPDATE, row-level: 1(row)|2(before)|4(insert)|16(update) = 23
    timing, events = _decode(23)
    assert timing == "BEFORE"
    assert events == ["INSERT", "UPDATE"]
    # INSTEAD OF DELETE: 64(instead)|8(delete)|1 = 73
    timing, events = _decode(73)
    assert timing == "INSTEAD OF"
    assert "DELETE" in events
