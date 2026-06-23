"""PostgreSQL connection management built on psycopg (psycopg3)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ..config import Config
from ..logging_config import get_logger

log = get_logger(__name__)

Params = Sequence[Any] | Mapping[str, Any] | None


class Database:
    """Thin wrapper around a psycopg connection exposing dict-row queries."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    @classmethod
    @contextmanager
    def connect(cls, config: Config) -> Iterator[Database]:
        """Open a read-only connection for the lifetime of the context."""
        log.info("Connecting to database", extra={"host": config.host,
                                                   "database": config.database})
        conn = psycopg.connect(config.conninfo, autocommit=True)
        try:
            # We never write; advertise that to the server.
            with conn.cursor() as cur:
                cur.execute("SET default_transaction_read_only = on")
            yield cls(conn)
        finally:
            conn.close()
            log.info("Connection closed")

    def query(self, sql: str, params: Params = None) -> list[dict[str, Any]]:
        """Run a query returning a list of dict rows."""
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def query_one(self, sql: str, params: Params = None) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Params = None) -> Any:
        row = self.query_one(sql, params)
        if not row:
            return None
        return next(iter(row.values()))
