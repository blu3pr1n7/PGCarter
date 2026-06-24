"""Read-only profiling-query construction with hard safety guarantees.

Every query the analyzer can execute is built here. Two rules are enforced
mechanically by :func:`assert_safe`:

1. The statement is a single ``SELECT`` (optionally a ``WITH … SELECT``).
2. It contains no data- or schema-mutating keyword
   (INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE/GRANT/REVOKE/COPY/MERGE).

Identifiers are always quoted via :func:`pgcarter.sql.base.quote_ident`, and
string literals via :func:`quote_literal`, so schema-qualified names with mixed
case or reserved words are handled safely. ``.sql`` template files in
``queries/`` provide the larger statements; small per-column expressions are
assembled by the helper functions below.
"""

from __future__ import annotations

import re
from pathlib import Path

from pgcarter.sql.base import qualified, quote_ident

_QUERY_DIR = Path(__file__).parent / "queries"

# A leading SELECT or WITH…SELECT, ignoring leading comments/whitespace.
_SELECT_RE = re.compile(r"^\s*(with\b|select\b)", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"(?<![a-z_])(insert|update|delete|drop|truncate|alter|create|grant|"
    r"revoke|copy|merge|call|do|vacuum|analyze|reindex)(?![a-z_])",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    """Raised when generated SQL is not a pure read-only SELECT."""


def assert_safe(sql: str) -> str:
    """Validate that ``sql`` is a read-only SELECT; return it unchanged.

    Comments are stripped before the forbidden-keyword scan so that a column
    literally named ``update`` in a comment cannot trip the guard, while a real
    ``UPDATE`` statement still does.
    """
    scan = re.sub(r"--[^\n]*", "", sql)
    if not _SELECT_RE.match(scan):
        raise UnsafeQueryError(f"Query does not start with SELECT/WITH: {sql!r}")
    forbidden = _FORBIDDEN_RE.search(scan)
    if forbidden:
        raise UnsafeQueryError(
            f"Query contains forbidden keyword '{forbidden.group(0)}': {sql!r}"
        )
    return sql


def quote_literal(value: str) -> str:
    """Quote a string as a SQL literal (single quotes, doubled internally)."""
    return "'" + value.replace("'", "''") + "'"


def load_template(name: str) -> str:
    """Load a raw ``.sql`` template from the ``queries/`` directory."""
    return (_QUERY_DIR / name).read_text()


def render_template(name: str, **subs: str) -> str:
    """Load, substitute ``{placeholder}`` tokens, and safety-check a template."""
    return assert_safe(load_template(name).format(**subs))


# --- relation expressions ---------------------------------------------------


def relation(schema: str, table: str, sample_size: int | None = None) -> str:
    """A FROM-clause expression for a table, optionally row-capped.

    Sampling uses a ``LIMIT`` subquery rather than a sequential ``count(*)``,
    bounding the rows touched by expensive per-column aggregates. (LIMIT without
    ORDER BY reads at most ``sample_size`` rows.)
    """
    rel = qualified(schema, table)
    if sample_size is not None and sample_size > 0:
        return f"(SELECT * FROM {rel} LIMIT {int(sample_size)}) AS _sample"
    return rel


# --- per-column statement builders ------------------------------------------


def null_and_cardinality_sql(relation_expr: str, column: str) -> str:
    """Total rows, null rows, and distinct values for one column.

    Rendered from the external ``column_stats.sql`` template so the on-disk SQL
    is the single source of truth for this profile.
    """
    return render_template(
        "column_stats.sql",
        column=quote_ident(column),
        relation=relation_expr,
    )


def distribution_sql(relation_expr: str, column: str, *, numeric: bool = True) -> str:
    """min / max (and, for numeric columns, avg) of a column.

    ``avg`` is only emitted for numeric columns: averaging a temporal type via a
    ``double precision`` cast is not supported by PostgreSQL, so temporal columns
    report ``NULL`` for the average and rely on min/max for their range.
    """
    col = quote_ident(column)
    avg_expr = f"avg({col}::double precision)" if numeric else "NULL"
    sql = (
        "SELECT\n"
        f"    min({col}) AS min_value,\n"
        f"    max({col}) AS max_value,\n"
        f"    {avg_expr} AS avg_value\n"
        f"FROM {relation_expr}"
    )
    return assert_safe(sql)


def freshness_sql(relation_expr: str, column: str) -> str:
    """Earliest and latest value of a timestamp/date column."""
    col = quote_ident(column)
    sql = (
        "SELECT\n"
        f"    min({col}) AS earliest,\n"
        f"    max({col}) AS latest\n"
        f"FROM {relation_expr}"
    )
    return assert_safe(sql)


def string_profile_sql(relation_expr: str, column: str) -> str:
    """Average / minimum / maximum text length for a text column."""
    col = quote_ident(column)
    sql = (
        "SELECT\n"
        f"    avg(length({col}::text)) AS avg_length,\n"
        f"    min(length({col}::text)) AS min_length,\n"
        f"    max(length({col}::text)) AS max_length\n"
        f"FROM {relation_expr}"
    )
    return assert_safe(sql)


def value_distribution_sql(relation_expr: str, column: str, limit: int = 20) -> str:
    """Top distinct values by frequency (for status/enum-like columns)."""
    col = quote_ident(column)
    sql = (
        f"SELECT {col} AS value, count(*) AS frequency\n"
        f"FROM {relation_expr}\n"
        f"GROUP BY {col}\n"
        "ORDER BY count(*) DESC\n"
        f"LIMIT {int(limit)}"
    )
    return assert_safe(sql)


def duplicate_values_sql(relation_expr: str, column: str) -> str:
    """Count of values that appear more than once in a (supposedly unique) column."""
    col = quote_ident(column)
    sql = (
        "SELECT count(*) AS duplicate_groups, coalesce(sum(c) - count(*), 0) AS extra_rows\n"
        "FROM (\n"
        f"    SELECT {col}, count(*) AS c\n"
        f"    FROM {relation_expr}\n"
        f"    WHERE {col} IS NOT NULL\n"
        f"    GROUP BY {col}\n"
        "    HAVING count(*) > 1\n"
        ") d"
    )
    return assert_safe(sql)
