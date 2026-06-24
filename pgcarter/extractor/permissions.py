"""Privilege (GRANT) extraction across object classes.

Uses ``aclexplode`` over the relevant catalog ACL columns so every explicit
grant (database, schema, table, column, sequence, function) is captured in a
single uniform :class:`~pgcarter.models.Grant` shape.
"""

from __future__ import annotations

from pgcarter.extractor.base import Extractor
from pgcarter.models import Grant

_GRANTEE = (
    "CASE WHEN acl.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(acl.grantee) END"
)

_DATABASE = f"""
SELECT
    current_database()        AS object_name,
    {_GRANTEE}                AS grantee,
    acl.privilege_type        AS privilege,
    acl.is_grantable          AS grantable
FROM pg_catalog.pg_database d,
     LATERAL aclexplode(d.datacl) AS acl
WHERE d.datname = current_database()
ORDER BY grantee, privilege
"""

_SCHEMA = f"""
SELECT
    n.nspname                 AS object_name,
    {_GRANTEE}                AS grantee,
    acl.privilege_type        AS privilege,
    acl.is_grantable          AS grantable
FROM pg_catalog.pg_namespace n,
     LATERAL aclexplode(n.nspacl) AS acl
WHERE n.nspname = ANY(%(schemas)s)
ORDER BY object_name, grantee, privilege
"""

_RELATION = f"""
SELECT
    n.nspname || '.' || c.relname AS object_name,
    CASE WHEN c.relkind = 'S' THEN 'sequence' ELSE 'table' END AS object_type,
    {_GRANTEE}                AS grantee,
    acl.privilege_type        AS privilege,
    acl.is_grantable          AS grantable
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace,
     LATERAL aclexplode(c.relacl) AS acl
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S')
  AND n.nspname = ANY(%(schemas)s)
ORDER BY object_name, grantee, privilege
"""

_COLUMN = f"""
SELECT
    n.nspname || '.' || c.relname AS object_name,
    a.attname                 AS column_name,
    {_GRANTEE}                AS grantee,
    acl.privilege_type        AS privilege,
    acl.is_grantable          AS grantable
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace,
     LATERAL aclexplode(a.attacl) AS acl
WHERE a.attacl IS NOT NULL
  AND a.attnum > 0
  AND n.nspname = ANY(%(schemas)s)
ORDER BY object_name, column_name, grantee, privilege
"""

_FUNCTION = f"""
SELECT
    n.nspname || '.' || p.proname
        || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')'
                              AS object_name,
    {_GRANTEE}                AS grantee,
    acl.privilege_type        AS privilege,
    acl.is_grantable          AS grantable
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace,
     LATERAL aclexplode(p.proacl) AS acl
WHERE n.nspname = ANY(%(schemas)s)
ORDER BY object_name, grantee, privilege
"""


class PermissionExtractor(Extractor):
    name = "permission"

    def extract(self) -> list[Grant]:
        params = {"schemas": self.schemas}
        grants: list[Grant] = []

        for r in self.db.query(_DATABASE):
            grants.append(self._grant("database", r["object_name"], r))
        for r in self.db.query(_SCHEMA, params):
            grants.append(self._grant("schema", r["object_name"], r))
        for r in self.db.query(_RELATION, params):
            grants.append(self._grant(r["object_type"], r["object_name"], r))
        for r in self.db.query(_COLUMN, params):
            grants.append(self._grant("column", r["object_name"], r, column=r["column_name"]))
        for r in self.db.query(_FUNCTION, params):
            grants.append(self._grant("function", r["object_name"], r))

        self.report.record_extracted("grants", len(grants))
        return grants

    @staticmethod
    def _grant(object_type: str, object_name: str, row: dict, column: str | None = None) -> Grant:
        return Grant(
            object_type=object_type,
            object_name=object_name,
            grantee=row["grantee"],
            privilege=row["privilege"],
            grantable=row["grantable"],
            column=column,
        )
