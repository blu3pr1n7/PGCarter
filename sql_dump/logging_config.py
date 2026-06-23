"""Structured l# Connection details for the dockerised test database (see docker-compose.yml).
export SQLDUMP_TEST_HOST ?= localhost
export SQLDUMP_TEST_PORT ?= 55432
export SQLDUMP_TEST_DB   ?= sqldump_test
export SQLDUMP_TEST_USER ?= sqldump
export SQLDUMP_TEST_PASSWORD ?= sqldumpogging configuration for sql-dump."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Include any structured extras attached to the record.
        for key, value in record.__dict__.items():
            if key in ("args", "msg", "levelname", "levelno", "pathname", "filename",
                       "module", "exc_info", "exc_text", "stack_info", "lineno",
                       "funcName", "created", "msecs", "relativeCreated", "thread",
                       "threadName", "processName", "process", "name", "taskName"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, json_format: bool = False) -> None:
    """Configure the root logger for the application.

    Args:
        level: Logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
        json_format: If True, emit structured JSON logs; otherwise human-readable.
    """
    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
