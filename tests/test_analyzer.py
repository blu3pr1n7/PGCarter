"""Tests for the database analysis / profiling subsystem.

Covers, with no live database required:
  * SQL-safety guarantees and read-only query generation
  * column name/type heuristics
  * configuration loading (YAML) and check enable/disable
  * offline JSON inventory loading and structural analysis
  * online profiling against a fake database
  * JSON + Markdown output writing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pgcarter.analyzer import heuristics
from pgcarter.analyzer.config import AnalysisConfig, load_analysis_config
from pgcarter.analyzer.engine import AnalysisEngine
from pgcarter.analyzer.loader import InventoryLoadError, load_inventory
from pgcarter.analyzer.models import CRITICAL
from pgcarter.analyzer.queries import (
    UnsafeQueryError,
    assert_safe,
    duplicate_values_sql,
    null_and_cardinality_sql,
    quote_literal,
    relation,
    string_profile_sql,
    value_distribution_sql,
)
from pgcarter.analyzer.rules import (
    constraint_columns,
    instantiate_checks,
    registered_checks,
)
from pgcarter.analyzer.writer import write_analysis
from pgcarter.models import Constraint
from pgcarter.report import Report
from pgcarter.writers.json_writer import JsonWriter

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


# --------------------------------------------------------------------------- #
# SQL safety + generation
# --------------------------------------------------------------------------- #


def test_assert_safe_accepts_select():
    assert_safe("SELECT count(*) FROM public.users")
    assert_safe("  WITH x AS (SELECT 1) SELECT * FROM x")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET x = 1",
        "DELETE FROM users",
        "DROP TABLE users",
        "INSERT INTO users VALUES (1)",
        "TRUNCATE users",
        "SELECT 1; DROP TABLE users",
        "ALTER TABLE users ADD COLUMN x int",
    ],
)
def test_assert_safe_rejects_mutations(sql):
    with pytest.raises(UnsafeQueryError):
        assert_safe(sql)


def test_query_builders_are_safe_and_quoted():
    rel = relation("public", "user")  # 'user' is reserved -> must be quoted
    assert rel == 'public."user"'
    sql = null_and_cardinality_sql(rel, "select")  # reserved column name
    assert "SELECT" in sql
    assert '"select"' in sql
    assert_safe(sql)  # does not raise (read-only despite leading comment)


def test_sampling_wraps_in_limit_subquery():
    rel = relation("public", "orders", sample_size=5000)
    assert "LIMIT 5000" in rel
    assert rel.endswith("AS _sample")
    sql = string_profile_sql(rel, "notes")
    assert "LIMIT 5000" in sql
    assert_safe(sql)


def test_value_distribution_and_duplicates_are_select_only():
    assert_safe(value_distribution_sql(relation("public", "t"), "status"))
    assert_safe(duplicate_values_sql(relation("public", "t"), "email"))


def test_quote_literal_escapes_quotes():
    assert quote_literal("O'Brien") == "'O''Brien'"


# --------------------------------------------------------------------------- #
# Heuristics
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["id", "user_id", "uuid", "order_uuid"])
def test_identifier_names(name):
    assert heuristics.is_identifier_name(name)


@pytest.mark.parametrize("name", ["created_at", "updated_at", "deleted_at", "inserted_at"])
def test_timestamp_names(name):
    assert heuristics.is_timestamp_name(name)


def test_email_and_status_names():
    assert heuristics.is_email_name("email")
    assert heuristics.is_email_name("email_address")
    assert heuristics.is_status_name("status")
    assert heuristics.is_status_name("order_type")


def test_type_families():
    assert heuristics.is_numeric("integer")
    assert heuristics.is_numeric("numeric(10,2)")
    assert heuristics.is_temporal("timestamp without time zone")
    assert heuristics.is_text("character varying(255)")
    assert heuristics.is_boolean("boolean")
    assert heuristics.supports_aggregates("bigint")
    assert not heuristics.supports_aggregates("text")


def test_constraint_column_parsing_from_definition():
    fk = Constraint(
        name="t_fk",
        schema="public",
        table="t",
        type="FOREIGN KEY",
        definition="FOREIGN KEY (user_id) REFERENCES users(id)",
    )
    assert constraint_columns(fk) == ["user_id"]
    pk = Constraint(
        name="t_pk",
        schema="public",
        table="t",
        type="PRIMARY KEY",
        definition="PRIMARY KEY (id)",
    )
    assert constraint_columns(pk) == ["id"]


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def test_load_config_defaults_when_absent():
    cfg = load_analysis_config(None)
    assert cfg.enabled_checks is None  # all enabled
    assert cfg.thresholds.high_null_percentage == 80.0
    assert cfg.is_enabled("anything")


def test_load_config_from_yaml(tmp_path):
    path = tmp_path / "analysis.yml"
    path.write_text(
        "analysis:\n"
        "  enabled_checks:\n"
        "    - null_analysis\n"
        "    - table_size\n"
        "  thresholds:\n"
        "    high_null_percentage: 50\n"
        "    low_cardinality_limit: 3\n"
    )
    cfg = load_analysis_config(path, sample_size=1234)
    assert cfg.enabled_checks == ["null_analysis", "table_size"]
    assert cfg.thresholds.high_null_percentage == 50
    assert cfg.thresholds.low_cardinality_limit == 3
    assert cfg.sample_size == 1234  # CLI override applied
    assert cfg.is_enabled("null_analysis")
    assert not cfg.is_enabled("cardinality")


def test_enabled_checks_filters_instantiation():
    cfg = AnalysisConfig(enabled_checks=["null_analysis", "table_size"])
    checks = instantiate_checks(cfg)
    assert {c.name for c in checks} == {"null_analysis", "table_size"}
    # The registry holds every check regardless of config.
    assert len(registered_checks()) > len(checks)


# --------------------------------------------------------------------------- #
# Offline analysis
# --------------------------------------------------------------------------- #


def test_loader_roundtrips_inventory(tmp_path, sample_inventory):
    JsonWriter(tmp_path / "json", Report()).write(sample_inventory)
    inv = load_inventory(tmp_path)
    assert inv.database.name == "shop"
    assert [t.name for t in inv.tables] == ["customer"]
    table = inv.tables[0]
    assert {c.name for c in table.columns} == {"id", "email", "created_at", "full_name"}
    assert any(c.type == "FOREIGN KEY" for c in table.constraints)


def test_loader_missing_directory_raises(tmp_path):
    with pytest.raises(InventoryLoadError):
        load_inventory(tmp_path / "does-not-exist")


def test_offline_analysis_is_structural(sample_inventory):
    report = AnalysisEngine(sample_inventory, AnalysisConfig()).analyze()
    assert report.mode == "offline"
    assert report.database == "shop"
    assert len(report.tables) == 1

    # The FK on (org_id) has no covering index -> a structural warning offline.
    warning_checks = {w.check for w in report.warnings}
    assert "missing_fk_indexes" in warning_checks

    # Column semantics are inferred from names/types without a database.
    customer = report.tables[0]
    by_name = {c.name: c for c in customer.columns}
    assert "identifier" in by_name["id"].semantics
    assert "email" in by_name["email"].semantics
    assert "timestamp" in by_name["created_at"].semantics


def test_offline_records_queries_without_executing(sample_inventory):
    engine = AnalysisEngine(sample_inventory, AnalysisConfig())
    engine.analyze()
    # Online-only checks still generate (and record) the SQL they would run.
    assert engine.ctx.generated_queries
    for sql in engine.ctx.generated_queries:
        assert_safe(sql)  # everything generated is read-only


# --------------------------------------------------------------------------- #
# Online analysis (fake database)
# --------------------------------------------------------------------------- #


class FakeDB:
    """Canned profiling responses keyed by a marker substring in each query."""

    RESPONSES: dict[str, list[dict[str, Any]]] = {
        "pg_total_relation_size": [
            {
                "total_bytes": 4096000,
                "table_bytes": 3000000,
                "index_bytes": 1096000,
                "total_pretty": "4000 kB",
                "table_pretty": "2930 kB",
                "index_pretty": "1070 kB",
                "estimated_rows": 1000,
            }
        ],
        "FILTER (WHERE": [
            {"total_rows": 1000, "null_rows": 50, "distinct_values": 900},
        ],
        "avg_value": [{"min_value": 1, "max_value": 100, "avg_value": 50.0}],
        "avg_length": [{"avg_length": 12.5, "min_length": 3, "max_length": 40}],
        "earliest": [{"earliest": "2020-01-01", "latest": "2024-01-01"}],
        "frequency": [
            {"value": "active", "frequency": 900},
            {"value": "inactive", "frequency": 100},
        ],
        "duplicate_groups": [{"duplicate_groups": 0, "extra_rows": 0}],
        "orphans": [{"orphans": 0}],
        "pg_stat_user_indexes": [],
    }

    def query(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        for marker, rows in self.RESPONSES.items():
            if marker in sql:
                return rows
        return []


def test_online_analysis_enriches_with_stats(sample_inventory):
    report = AnalysisEngine(sample_inventory, AnalysisConfig(), db=FakeDB()).analyze()
    assert report.mode == "online"
    table = report.tables[0]

    # Table-level metrics come from pg_total_relation_size / reltuples.
    assert table.metrics["estimated_rows"] == 1000
    assert table.metrics["total_size"] == "4000 kB"

    # Column stats come from the profiling queries.
    email = next(c for c in table.columns if c.name == "email")
    assert email.stats["null_percentage"] == 5.0  # 50 / 1000
    assert email.stats["distinct_values"] == 900


def test_permission_denied_is_skipped_not_fatal(sample_inventory):
    """A permission error logs-and-skips the relation; the run still succeeds."""
    import psycopg

    class DeniedDB:
        def __init__(self) -> None:
            self.calls = 0

        def query(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
            self.calls += 1
            raise psycopg.errors.InsufficientPrivilege("permission denied for table customer")

    db = DeniedDB()
    run_report = Report()
    report = AnalysisEngine(sample_inventory, AnalysisConfig(), db=db, report=run_report).analyze()

    # No run errors — the denial is recorded as a skip, not an error.
    assert run_report.errors == []
    assert report.mode == "online"
    # The relation is recorded exactly once, not once per failing query/column.
    customer_skips = [s for s in run_report.skipped if s.object_name == "customer"]
    assert len(customer_skips) == 1
    assert "permission denied" in customer_skips[0].reason


def test_online_detects_critical_duplicate(sample_inventory):
    class DupDB(FakeDB):
        RESPONSES = {
            **FakeDB.RESPONSES,
            "duplicate_groups": [
                {"duplicate_groups": 2, "extra_rows": 3},
            ],
        }

    report = AnalysisEngine(sample_inventory, AnalysisConfig(), db=DupDB()).analyze()
    severities = {w.severity for w in report.warnings}
    assert CRITICAL in severities
    assert any(w.check == "duplicate_unique_values" for w in report.warnings)


def test_sample_size_threads_into_generated_sql(sample_inventory):
    cfg = AnalysisConfig(sample_size=2500)
    engine = AnalysisEngine(sample_inventory, cfg, db=FakeDB())
    engine.analyze()
    assert any("LIMIT 2500" in q for q in engine.ctx.generated_queries)


# --------------------------------------------------------------------------- #
# Output writing
# --------------------------------------------------------------------------- #


def test_write_analysis_emits_json_and_docs(tmp_path, sample_inventory):
    report = AnalysisEngine(sample_inventory, AnalysisConfig()).analyze()
    analysis_dir = tmp_path / "analysis"
    docs_dir = analysis_dir / "docs" / "analysis"
    write_analysis(
        report,
        analysis_dir=analysis_dir,
        docs_dir=docs_dir,
        templates_dir=TEMPLATES_DIR,
    )

    report_json = json.loads((analysis_dir / "report.json").read_text())
    assert report_json["database"] == "shop"
    assert (analysis_dir / "warnings.json").is_file()
    assert (analysis_dir / "tables" / "customer.json").is_file()

    # Documentation is rendered from external templates (no embedded Markdown).
    assert (docs_dir / "index.md").is_file()
    assert (docs_dir / "warnings.md").is_file()
    assert (docs_dir / "tables" / "customer.md").is_file()
    assert "# Analysis: public.customer" in (docs_dir / "tables" / "customer.md").read_text()


def test_write_analysis_skips_docs_without_templates(tmp_path, sample_inventory):
    report = AnalysisEngine(sample_inventory, AnalysisConfig()).analyze()
    run_report = Report()
    write_analysis(
        report,
        analysis_dir=tmp_path / "a",
        docs_dir=tmp_path / "a" / "docs",
        templates_dir=tmp_path / "no-templates",
        report=run_report,
    )
    assert (tmp_path / "a" / "report.json").is_file()
    assert not (tmp_path / "a" / "docs").exists()
    assert run_report.warnings  # records that docs were skipped


def test_no_table_data_in_generated_sql(sample_inventory):
    """Every generated statement is a read-only SELECT — never DML/DDL."""
    engine = AnalysisEngine(sample_inventory, AnalysisConfig(), db=FakeDB())
    engine.analyze()
    for sql in engine.ctx.generated_queries:
        upper = sql.upper()
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "COPY "):
            assert forbidden not in upper
