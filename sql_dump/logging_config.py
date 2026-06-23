"""Structured logging configuration for sql-dump, built on ``structlog``.

Production default: line-delimited **JSON to stdout**, ready for ingestion by log
aggregators (Datadog, ELK/OpenSearch, CloudWatch, Loki, …). Enable colourised
developer console output with ``pretty_logs=True`` or ``LOG_PRETTY=true``.

Both stdlib ``logging.getLogger`` and ``structlog.get_logger`` are supported and
render through the *same* pipeline, so existing ``%``-style calls keep working
while new code can emit structured key/value events. Context bound via
``structlog.contextvars.bind_contextvars`` (e.g. ``request_id``) is automatically
attached to every event.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

_TRUE = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def _shared_processors() -> list[Any]:
    """Processors applied to *every* event, structlog- or stdlib-originated."""
    return [
        # Merge contextvars (service, environment, request_id, …) first.
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        # Render %-style positional args from legacy ``log.info("x %s", y)`` calls.
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
    ]


def configure_logging(
    pretty_logs: bool | None = None,
    level: str | None = None,
) -> None:
    """Configure structlog and stdlib logging for the whole application.

    Args:
        pretty_logs: ``True`` → colourised developer console; ``False`` → JSON.
            ``None`` (default) falls back to the ``LOG_PRETTY`` environment
            variable, then to JSON.
        level: Logging level name (``"DEBUG"``/``"INFO"``/…). ``None`` falls back
            to the ``LOG_LEVEL`` environment variable, then to ``"INFO"``.

    Logs are written to **stdout**. Calling this more than once reconfigures
    cleanly (the root handler is replaced).
    """
    if pretty_logs is None:
        pretty_logs = _env_bool("LOG_PRETTY", False)
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, str(level).upper(), logging.INFO)

    shared = _shared_processors()

    if pretty_logs:
        # ConsoleRenderer renders exc_info itself (pretty, coloured tracebacks).
        final_processors: list[Any] = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        # JSON mode: serialise exceptions into a string ``exception`` field.
        final_processors = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    # structlog-originated records run the shared chain then hand off to the
    # stdlib ProcessorFormatter for final rendering.
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # The single handler renders BOTH structlog and plain-stdlib records.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=final_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger (stdlib-compatible).

    Accepts ``%``-style positional args and ``.exception()`` like the stdlib
    logger it replaces, while also accepting structured keyword fields.
    """
    return structlog.get_logger(name)
