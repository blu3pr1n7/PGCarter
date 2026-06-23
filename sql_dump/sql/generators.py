"""Deterministic SQL (DDL) generation from metadata models.

Each function returns the *body* of a SQL statement (no provenance header). The
writer layer wraps these with :func:`sql_dump.sql.base.with_header`.
"""

from __future__ import annotations

from ..models import (
    Column,
    DatabaseInfo,
    Extension,
    Function,
    Grant,
    Index,
    Role,
    Schema,
    Sequence,
    Table,
    Trigger,
    View,
)
from .base import qualified, quote_ident

_CONSTRAINT_ORDER = {"PRIMARY KEY": 0, "UNIQUE": 1, "FOREIGN KEY": 2, "CHECK": 3, "EXCLUDE": 4}


def database_sql(db: DatabaseInfo) -> str:
    lines = [
        f"-- Database: {db.name}",
        f"-- Version: {db.version}",
        f"-- Owner: {db.owner}",
        "--",
        "-- Recreate with (run from an administrative connection):",
        f"CREATE DATABASE {quote_ident(db.name)}",
        f"    WITH OWNER = {quote_ident(db.owner)}",
        f"    ENCODING = '{db.encoding}'",
        f"    LC_COLLATE = '{db.collation}'",
        f"    LC_CTYPE = '{db.ctype}';",
    ]
    if db.comment:
        lines.append(
            f"COMMENT ON DATABASE {quote_ident(db.name)} IS {_lit(db.comment)};"
        )
    return "\n".join(lines)


def schema_sql(schema: Schema) -> str:
    lines = [f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema.name)}"
             f" AUTHORIZATION {quote_ident(schema.owner)};"]
    if schema.comment:
        lines.append(
            f"COMMENT ON SCHEMA {quote_ident(schema.name)} IS {_lit(schema.comment)};"
        )
    if schema.grants:
        lines.append("")
        lines.extend(grant_statements(schema.grants))
    return "\n".join(lines)


def _column_sql(col: Column) -> str:
    parts = [f"    {quote_ident(col.name)} {col.data_type}"]
    if col.is_generated and col.generation_expression:
        parts.append(f"GENERATED ALWAYS AS ({col.generation_expression}) STORED")
    elif col.is_identity:
        gen = col.identity_generation or "BY DEFAULT"
        parts.append(f"GENERATED {gen} AS IDENTITY")
    elif col.default is not None:
        parts.append(f"DEFAULT {col.default}")
    if not col.nullable and not col.is_identity:
        parts.append("NOT NULL")
    return " ".join(parts)


def table_sql(table: Table) -> str:
    lines: list[str] = [f"CREATE TABLE {qualified(table.schema, table.name)} ("]

    body_lines = [_column_sql(c) for c in table.columns]

    constraints = sorted(
        table.constraints, key=lambda c: (_CONSTRAINT_ORDER.get(c.type, 9), c.name)
    )
    for con in constraints:
        body_lines.append(f"    CONSTRAINT {quote_ident(con.name)} {con.definition}")

    lines.append(",\n".join(body_lines))
    lines.append(");")

    if table.comment:
        lines.append("")
        lines.append(
            f"COMMENT ON TABLE {qualified(table.schema, table.name)} "
            f"IS {_lit(table.comment)};"
        )
    for col in table.columns:
        if col.comment:
            lines.append(
                f"COMMENT ON COLUMN {qualified(table.schema, table.name)}."
                f"{quote_ident(col.name)} IS {_lit(col.comment)};"
            )
    return "\n".join(lines)


def index_sql(index: Index) -> str:
    return index.definition.rstrip(";") + ";"


def view_sql(view: View) -> str:
    keyword = "MATERIALIZED VIEW" if view.materialized else "VIEW"
    lines = [
        f"CREATE {keyword} {qualified(view.schema, view.name)} AS",
        view.definition.rstrip().rstrip(";") + ";",
    ]
    if view.comment:
        lines.append("")
        lines.append(
            f"COMMENT ON {keyword} {qualified(view.schema, view.name)} "
            f"IS {_lit(view.comment)};"
        )
    return "\n".join(lines)


def function_sql(func: Function) -> str:
    if not func.definition:
        return (
            f"-- {func.kind} {func.schema}.{func.signature} has no executable "
            "definition (aggregate/window forms are described in JSON only)."
        )
    body = func.definition.rstrip().rstrip(";") + ";"
    if func.comment:
        obj = "PROCEDURE" if func.kind == "procedure" else "FUNCTION"
        body += (
            f"\n\nCOMMENT ON {obj} {qualified(func.schema, func.name)}"
            f"({func.arguments}) IS {_lit(func.comment)};"
        )
    return body


def trigger_sql(trig: Trigger) -> str:
    return trig.definition.rstrip(";") + ";"


def sequence_create_sql(seq: Sequence) -> str:
    """CREATE SEQUENCE only (no OWNED BY); safe to run before tables exist."""
    lines = [
        f"CREATE SEQUENCE IF NOT EXISTS {qualified(seq.schema, seq.name)}",
        f"    AS {seq.data_type}",
        f"    INCREMENT BY {seq.increment}",
        f"    MINVALUE {seq.min_value}",
        f"    MAXVALUE {seq.max_value}",
        f"    START WITH {seq.start}",
        f"    CACHE {seq.cache}"
        + ("\n    CYCLE" if seq.cycle else ""),
    ]
    return "\n".join(lines) + ";"


def sequence_owned_by_sql(seq: Sequence) -> str | None:
    """The ALTER SEQUENCE ... OWNED BY statement (must run after the table)."""
    if not seq.owned_by:
        return None
    return f"ALTER SEQUENCE {qualified(seq.schema, seq.name)} OWNED BY {seq.owned_by};"


def sequence_sql(seq: Sequence) -> str:
    stmt = sequence_create_sql(seq)
    owned = sequence_owned_by_sql(seq)
    if owned:
        stmt += "\n" + owned
    return stmt


def extensions_sql(extensions: list[Extension]) -> str:
    lines = []
    for ext in extensions:
        lines.append(
            f"CREATE EXTENSION IF NOT EXISTS {quote_ident(ext.name)} "
            f"WITH SCHEMA {quote_ident(ext.schema)} VERSION '{ext.version}';"
        )
    return "\n".join(lines)


def roles_sql(roles: list[Role]) -> str:
    lines: list[str] = []
    for role in roles:
        opts = []
        opts.append("SUPERUSER" if role.superuser else "NOSUPERUSER")
        opts.append("CREATEDB" if role.createdb else "NOCREATEDB")
        opts.append("CREATEROLE" if role.createrole else "NOCREATEROLE")
        opts.append("INHERIT" if role.inherit else "NOINHERIT")
        opts.append("LOGIN" if role.login else "NOLOGIN")
        opts.append("REPLICATION" if role.replication else "NOREPLICATION")
        if role.connection_limit != -1:
            opts.append(f"CONNECTION LIMIT {role.connection_limit}")
        # Roles are cluster-global; guard creation so the script is re-runnable.
        lines.append(
            f"DO $do$ BEGIN\n"
            f"    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {_lit(role.name)}) THEN\n"
            f"        CREATE ROLE {quote_ident(role.name)} WITH " + " ".join(opts) + ";\n"
            "    END IF;\nEND $do$;"
        )
        for parent in role.member_of:
            lines.append(f"GRANT {quote_ident(parent)} TO {quote_ident(role.name)};")
        if role.comment:
            lines.append(
                f"COMMENT ON ROLE {quote_ident(role.name)} IS {_lit(role.comment)};"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _grant_target(grant: Grant) -> str:
    if grant.object_type == "database":
        return f"DATABASE {quote_ident(grant.object_name)}"
    if grant.object_type == "schema":
        return f"SCHEMA {quote_ident(grant.object_name)}"
    if grant.object_type == "sequence":
        return f"SEQUENCE {grant.object_name}"
    if grant.object_type == "function":
        return f"FUNCTION {grant.object_name}"
    # table / column both target the table relation
    return f"TABLE {grant.object_name}"


def grant_statements(grants: list[Grant]) -> list[str]:
    """Render GRANT statements, collapsing column privileges per (grantee, priv)."""
    statements: list[str] = []
    for grant in sorted(
        grants, key=lambda g: (g.object_type, g.object_name, g.grantee, g.privilege)
    ):
        target = _grant_target(grant)
        priv = grant.privilege
        if grant.object_type == "column" and grant.column:
            priv = f"{grant.privilege} ({grant.column})"
        suffix = " WITH GRANT OPTION" if grant.grantable else ""
        grantee = "PUBLIC" if grant.grantee == "PUBLIC" else quote_ident(grant.grantee)
        statements.append(f"GRANT {priv} ON {target} TO {grantee}{suffix};")
    return statements


def permissions_sql(grants: list[Grant]) -> str:
    if not grants:
        return "-- No explicit privileges extracted."
    return "\n".join(grant_statements(grants))


def _lit(text: str) -> str:
    """Render a safe single-quoted SQL string literal."""
    return "'" + text.replace("'", "''") + "'"
