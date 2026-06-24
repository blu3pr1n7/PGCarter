"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from pgcarter.models import (
    Column,
    Constraint,
    DatabaseInfo,
    Extension,
    Function,
    Grant,
    Index,
    Inventory,
    Parameter,
    Relationship,
    Role,
    Schema,
    Sequence,
    Table,
    Trigger,
    View,
)


@pytest.fixture
def sample_table() -> Table:
    return Table(
        schema="public",
        name="customer",
        owner="app",
        comment="Customers of the shop",
        columns=[
            Column(
                name="id",
                position=1,
                data_type="bigint",
                nullable=False,
                is_identity=True,
                identity_generation="BY DEFAULT",
            ),
            Column(name="email", position=2, data_type="text", nullable=False),
            Column(
                name="created_at",
                position=3,
                data_type="timestamptz",
                nullable=False,
                default="now()",
            ),
            Column(
                name="full_name",
                position=4,
                data_type="text",
                nullable=True,
                is_generated=True,
                generation_expression="email",
            ),
        ],
        constraints=[
            Constraint(
                name="customer_pkey",
                schema="public",
                table="customer",
                type="PRIMARY KEY",
                definition="PRIMARY KEY (id)",
            ),
            Constraint(
                name="customer_email_key",
                schema="public",
                table="customer",
                type="UNIQUE",
                definition="UNIQUE (email)",
            ),
            Constraint(
                name="customer_org_fk",
                schema="public",
                table="customer",
                type="FOREIGN KEY",
                definition="FOREIGN KEY (org_id) REFERENCES public.org(id)",
                referenced_schema="public",
                referenced_table="org",
            ),
        ],
        grants=[
            Grant(
                object_type="table",
                object_name="public.customer",
                grantee="readonly",
                privilege="SELECT",
            ),
        ],
    )


@pytest.fixture
def sample_inventory(sample_table: Table) -> Inventory:
    return Inventory(
        database=DatabaseInfo(
            name="shop",
            version="16.2",
            encoding="UTF8",
            collation="en_US.UTF-8",
            ctype="en_US.UTF-8",
            owner="postgres",
            comment="Demo database",
        ),
        schemas=[Schema(name="public", owner="postgres", comment="standard public schema")],
        tables=[sample_table],
        indexes=[
            Index(
                schema="public",
                name="customer_pkey",
                table="customer",
                definition="CREATE UNIQUE INDEX customer_pkey ON public.customer USING btree (id)",
                is_unique=True,
                is_primary=True,
                is_constraint=True,
            ),
            Index(
                schema="public",
                name="customer_email_idx",
                table="customer",
                definition="CREATE INDEX customer_email_idx ON public.customer USING btree (email)",
                columns=["email"],
            ),
        ],
        views=[
            View(
                schema="public",
                name="active_customer",
                owner="app",
                definition="SELECT id, email FROM customer",
                columns=["id", "email"],
            ),
        ],
        functions=[
            Function(
                schema="public",
                name="greet",
                kind="function",
                signature="greet(name text)",
                arguments="name text",
                return_type="text",
                language="sql",
                volatility="IMMUTABLE",
                security_definer=False,
                owner="app",
                definition="CREATE OR REPLACE FUNCTION public.greet(name text)\n"
                " RETURNS text LANGUAGE sql AS $$ SELECT 'hi ' || name $$",
                parameters=[Parameter(name="name", mode="IN", data_type="text")],
            ),
        ],
        triggers=[
            Trigger(
                schema="public",
                name="customer_audit",
                table="customer",
                definition="CREATE TRIGGER customer_audit AFTER INSERT ON public.customer "
                "FOR EACH ROW EXECUTE FUNCTION audit()",
                timing="AFTER",
                events=["INSERT"],
                function="public.audit",
            ),
        ],
        sequences=[
            Sequence(
                schema="public",
                name="customer_id_seq",
                owner="app",
                data_type="bigint",
                start=1,
                increment=1,
                min_value=1,
                max_value=9223372036854775807,
                cache=1,
                cycle=False,
                owned_by="public.customer.id",
            ),
        ],
        extensions=[Extension(name="pgcrypto", version="1.3", schema="public")],
        roles=[
            Role(name="app", login=True),
            Role(name="readonly", login=True, inherit=True),
        ],
        grants=[
            Grant(object_type="schema", object_name="public", grantee="app", privilege="USAGE"),
            Grant(
                object_type="table",
                object_name="public.customer",
                grantee="readonly",
                privilege="SELECT",
            ),
            Grant(
                object_type="database", object_name="shop", grantee="PUBLIC", privilege="CONNECT"
            ),
        ],
        relationships=[
            Relationship(
                source="public.customer",
                target="public.org",
                type="foreign_key",
                label="customer_org_fk",
            ),
        ],
    )
