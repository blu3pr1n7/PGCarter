"""Integration tests against a live PostgreSQL database.

These are skipped unless a connection is configured via environment variables.
Set the following to enable (all but password are required):

    SQLDUMP_TEST_HOST, SQLDUMP_TEST_PORT, SQLDUMP_TEST_DB,
    SQLDUMP_TEST_USER, SQLDUMP_TEST_PASSWORD

Example:
    SQLDUMP_TEST_HOST=localhost SQLDUMP_TEST_DB=postgres \\
    SQLDUMP_TEST_USER=postgres pytest -m integration
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sql_dump.analyzer import AnalysisEngine, load_analysis_config
from sql_dump.config import resolve_config
from sql_dump.extractor import Database, InventoryExtractor
from sql_dump.main import run
from sql_dump.report import Report

pytestmark = pytest.mark.integration

_REQUIRED = ("SQLDUMP_TEST_HOST", "SQLDUMP_TEST_DB", "SQLDUMP_TEST_USER")


def _config(tmp_path: Path):
    if not all(os.environ.get(k) for k in _REQUIRED):
        pytest.skip("Live PostgreSQL connection not configured (SQLDUMP_TEST_* unset)")
    templates = Path(__file__).resolve().parents[1] / "templates"
    return resolve_config(
        host=os.environ["SQLDUMP_TEST_HOST"],
        port=int(os.environ.get("SQLDUMP_TEST_PORT", "5432")),
        database=os.environ["SQLDUMP_TEST_DB"],
        user=os.environ["SQLDUMP_TEST_USER"],
        password=os.environ.get("SQLDUMP_TEST_PASSWORD"),
        output_dir=str(tmp_path / "inventory"),
        templates_dir=str(templates),
    )


def test_full_run_against_live_db(tmp_path):
    config = _config(tmp_path)
    report = run(config)

    assert config.report_path.is_file()
    assert (config.sql_dir / "database.sql").is_file()
    assert (config.json_dir / "database.json").is_file()

    db = json.loads((config.json_dir / "database.json").read_text())
    assert db["name"] == config.database

    # report.json must be valid and self-consistent
    rep = json.loads(config.report_path.read_text())
    assert rep["database"] == config.database
    assert "summary" in rep
    assert report.errors == rep["errors"]


def test_no_data_exported(tmp_path):
    """The tool must only emit DDL/metadata, never row data.

    Function/trigger *definitions* may legitimately contain DML in their bodies,
    so the guarantee is checked precisely: no ``COPY ... FROM stdin`` data
    blocks anywhere, and no ``INSERT INTO`` in table DDL files.
    """
    config = _config(tmp_path)
    run(config)

    for sql_file in config.sql_dir.rglob("*.sql"):
        upper = sql_file.read_text().upper()
        assert "FROM STDIN" not in upper
        assert "COPY " not in upper

    tables_glob = config.sql_dir / "schemas"
    for table_file in tables_glob.rglob("tables/*.sql"):
        assert "INSERT INTO" not in table_file.read_text().upper()


def test_online_analysis_against_live_db(tmp_path):
    """Online analysis enriches structure with real profiling statistics."""
    config = _config(tmp_path)
    report = Report()
    analysis_cfg = load_analysis_config(None, sample_size=10000)

    with Database.connect(config) as db:
        inventory = InventoryExtractor(db, config.schemas, report).extract()
        analysis = AnalysisEngine(inventory, analysis_cfg, db=db, report=report).analyze()

    assert analysis.mode == "online"
    assert analysis.tables, "expected at least one analysed table"

    # At least one table should have measured size/row metrics from the DB.
    assert any("estimated_rows" in t.metrics for t in analysis.tables)
    # At least one column should carry executed profiling stats.
    assert any(
        c.stats for t in analysis.tables for c in t.columns
    ), "expected profiling statistics on some column"


def test_offline_analysis_from_inventory_json(tmp_path):
    """Running the extractor then analysing its JSON output works offline."""
    from sql_dump.analyzer import load_inventory

    config = _config(tmp_path)
    run(config)  # produces <output>/json/*.json

    inventory = load_inventory(config.output_dir)
    engine = AnalysisEngine(inventory, load_analysis_config(None))
    analysis = engine.analyze()
    assert analysis.mode == "offline"
    assert analysis.database == config.database
    # Every query the offline run generated is read-only.
    from sql_dump.analyzer.queries import assert_safe

    for sql in engine.ctx.generated_queries:
        assert_safe(sql)
