"""Tests for CLI argument parsing, config defaults, and the report model."""

from __future__ import annotations

from pathlib import Path

from sql_dump.cli import build_parser
from sql_dump.config import resolve_config
from sql_dump.report import Report


def test_output_dir_defaults_to_database_name():
    cfg = resolve_config(
        host="h", port=5432, database="mydb", user="u", password="p",
        output_dir=None, templates_dir=None,
    )
    assert cfg.output_dir == Path("mydb")


def test_templates_dir_default():
    cfg = resolve_config(
        host="h", port=5432, database="mydb", user="u", password="p",
        output_dir="out", templates_dir=None,
    )
    assert cfg.templates_dir == Path("./templates")


def test_password_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "fromenv")
    cfg = resolve_config(
        host="h", port=5432, database="mydb", user="u", password=None,
        output_dir="out", templates_dir="t",
    )
    assert cfg.password == "fromenv"


def test_conninfo_includes_core_fields():
    cfg = resolve_config(
        host="h", port=5433, database="mydb", user="u", password="secret",
        output_dir="out", templates_dir="t",
    )
    info = cfg.conninfo
    assert "host=h" in info
    assert "port=5433" in info
    assert "dbname=mydb" in info
    assert "password=secret" in info


def test_parser_requires_database():
    parser = build_parser()
    ns = parser.parse_args(["--database", "db"])
    assert ns.database == "db"
    assert ns.port == 5432


def test_parser_repeatable_schema():
    parser = build_parser()
    ns = parser.parse_args(["--database", "db", "--schema", "public", "--schema", "app"])
    assert ns.schemas == ["public", "app"]


def test_report_accumulates_and_serialises(tmp_path):
    report = Report(database="db")
    report.record_extracted("tables", 3)
    report.record_skipped("function", "f()", "no def")
    report.record_warning("a warning")
    report.record_error("an error")
    report.finish()
    out = tmp_path / "report.json"
    report.write(out)
    assert out.is_file()
    d = report.to_dict()
    assert d["summary"]["extracted"]["tables"] == 3
    assert d["summary"]["skipped_count"] == 1
    assert d["summary"]["error_count"] == 1
