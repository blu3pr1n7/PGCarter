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

from sql_dump.config import resolve_config
from sql_dump.main import run

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
