"""Tests for CLI argument parsing, config defaults, and the report model."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pgcarter.cli import app
from pgcarter.config import resolve_config
from pgcarter.report import Report

runner = CliRunner()


def test_output_dir_defaults_to_database_name():
    cfg = resolve_config(
        host="h",
        port=5432,
        database="mydb",
        user="u",
        password="p",
        output_dir=None,
        templates_dir=None,
    )
    assert cfg.output_dir == Path("mydb")


def test_templates_dir_default():
    cfg = resolve_config(
        host="h",
        port=5432,
        database="mydb",
        user="u",
        password="p",
        output_dir="out",
        templates_dir=None,
    )
    assert cfg.templates_dir == Path("./templates")


def test_password_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "fromenv")
    cfg = resolve_config(
        host="h",
        port=5432,
        database="mydb",
        user="u",
        password=None,
        output_dir="out",
        templates_dir="t",
    )
    assert cfg.password == "fromenv"


def test_conninfo_includes_core_fields():
    cfg = resolve_config(
        host="h",
        port=5433,
        database="mydb",
        user="u",
        password="secret",
        output_dir="out",
        templates_dir="t",
    )
    info = cfg.conninfo
    assert "host=h" in info
    assert "port=5433" in info
    assert "dbname=mydb" in info
    assert "password=secret" in info


def test_cli_exposes_index_and_analyze_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "index" in result.output
    assert "analyze" in result.output


def test_index_requires_database():
    # Missing the required --database option is a usage error (exit code 2).
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 2
    assert "database" in result.output.lower()


def test_analyze_requires_input_or_database():
    result = runner.invoke(app, ["analyze", "--output", "ignored"])
    assert result.exit_code != 0  # usage error: neither --input nor --database


def test_analyze_offline_runs_end_to_end(tmp_path, sample_inventory):
    from pgcarter.report import Report as _Report
    from pgcarter.writers.json_writer import JsonWriter

    inventory_dir = tmp_path / "inv"
    JsonWriter(inventory_dir / "json", _Report()).write(sample_inventory)
    out = tmp_path / "analysis"

    result = runner.invoke(
        app,
        [
            "analyze",
            "--input",
            str(inventory_dir),
            "--output",
            str(out),
            "--templates-dir",
            "./templates",
            "--log-level",
            "WARNING",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (out / "report.json").is_file()
    assert (out / "warnings.json").is_file()
    assert (out / "docs" / "analysis" / "index.md").is_file()


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
