"""Tests for the structlog-based logging configuration.

Covers JSON and pretty output modes, required fields, exception serialisation,
contextvars propagation, env-var configuration, and stdlib compatibility.
"""

from __future__ import annotations

import json
import logging

import pytest
import structlog

from sql_dump.logging_config import _env_bool, configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Keep contextvars/config from leaking between tests."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


def _json_lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


# --- JSON mode --------------------------------------------------------------


def test_json_mode_emits_pure_json_with_required_fields(capsys):
    configure_logging(pretty_logs=False, level="INFO")
    get_logger("test.json").info("user_created", user_id=123, plan="enterprise")

    lines = _json_lines(capsys.readouterr().out)
    assert len(lines) == 1
    record = lines[0]
    # Required fields.
    assert record["event"] == "user_created"
    assert record["level"] == "info"
    assert "timestamp" in record
    # Structured key/values are preserved (no string parsing required).
    assert record["user_id"] == 123
    assert record["plan"] == "enterprise"


def test_json_mode_goes_to_stdout_not_stderr(capsys):
    configure_logging(pretty_logs=False)
    get_logger("test.stdout").info("on_stdout")
    out = capsys.readouterr()
    assert "on_stdout" in out.out
    assert out.err == ""


def test_legacy_percent_style_still_works(capsys):
    configure_logging(pretty_logs=False)
    get_logger("test.legacy").info("Extracting %s", "public")
    record = _json_lines(capsys.readouterr().out)[0]
    assert record["event"] == "Extracting public"


# --- pretty mode ------------------------------------------------------------


def test_pretty_mode_is_not_json(capsys):
    configure_logging(pretty_logs=True, level="DEBUG")
    get_logger("test.pretty").info("user_created", user_id=123)
    out = capsys.readouterr().out
    assert "user_created" in out
    assert "user_id" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])


# --- exceptions -------------------------------------------------------------


def test_exception_serialises_in_json_mode(capsys):
    configure_logging(pretty_logs=False)
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("test.exc").exception("payment_failed", payment_id=123)

    record = _json_lines(capsys.readouterr().out)[0]
    assert record["event"] == "payment_failed"
    assert record["level"] == "error"
    assert record["payment_id"] == 123
    assert "exception" in record
    assert "ValueError" in record["exception"]
    assert "boom" in record["exception"]


# --- context variables ------------------------------------------------------


def test_contextvars_appear_in_every_event(capsys):
    configure_logging(pretty_logs=False)
    structlog.contextvars.bind_contextvars(service="sql-dump", request_id="abc123")
    get_logger("test.ctx").info("first")
    get_logger("test.ctx").info("second")

    records = _json_lines(capsys.readouterr().out)
    assert len(records) == 2
    for record in records:
        assert record["service"] == "sql-dump"
        assert record["request_id"] == "abc123"


# --- stdlib compatibility ---------------------------------------------------


def test_plain_stdlib_logger_renders_through_pipeline(capsys):
    configure_logging(pretty_logs=False)
    logging.getLogger("third.party").warning("stdlib message %d", 7)

    record = _json_lines(capsys.readouterr().out)[0]
    assert record["event"] == "stdlib message 7"
    assert record["level"] == "warning"
    assert "timestamp" in record


# --- environment configuration ----------------------------------------------


def test_env_pretty_toggles_mode(capsys, monkeypatch):
    monkeypatch.setenv("LOG_PRETTY", "true")
    configure_logging()  # no args → read env
    get_logger("test.env").info("hello")
    out = capsys.readouterr().out
    # Pretty (not JSON) because LOG_PRETTY=true.
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])


def test_env_level_sets_threshold(capsys, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()
    get_logger("test.level").info("suppressed_info")
    get_logger("test.level").warning("kept_warning")
    out = capsys.readouterr().out
    assert "suppressed_info" not in out
    assert "kept_warning" in out


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("1", True), ("YES", True), ("on", True),
     ("false", False), ("0", False), ("", False), (None, False)],
)
def test_env_bool(value, expected, monkeypatch):
    if value is None:
        monkeypatch.delenv("X_FLAG", raising=False)
    else:
        monkeypatch.setenv("X_FLAG", value)
    assert _env_bool("X_FLAG", False) is expected
