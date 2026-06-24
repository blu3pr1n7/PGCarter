"""Role extraction (cluster-wide)."""

from __future__ import annotations

from pgcarter.extractor.base import Extractor
from pgcarter.models import Role

_QUERY = """
SELECT
    r.rolname              AS name,
    r.rolsuper             AS superuser,
    r.rolcreatedb          AS createdb,
    r.rolcreaterole        AS createrole,
    r.rolinherit           AS inherit,
    r.rolcanlogin          AS login,
    r.rolreplication       AS replication,
    r.rolconnlimit         AS connection_limit,
    pg_catalog.shobj_description(r.oid, 'pg_authid') AS comment,
    ARRAY(
        SELECT g.rolname
        FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles g ON g.oid = m.roleid
        WHERE m.member = r.oid
        ORDER BY g.rolname
    )                      AS member_of
FROM pg_catalog.pg_roles r
WHERE r.rolname NOT LIKE 'pg\\_%'
ORDER BY r.rolname
"""


class RoleExtractor(Extractor):
    name = "role"

    def extract(self) -> list[Role]:
        roles: list[Role] = []
        try:
            rows = self.db.query(_QUERY)
        except Exception as exc:
            self.report.record_warning(f"Could not extract roles: {exc}")
            return roles
        for r in rows:
            roles.append(
                Role(
                    name=r["name"],
                    superuser=r["superuser"],
                    createdb=r["createdb"],
                    createrole=r["createrole"],
                    inherit=r["inherit"],
                    login=r["login"],
                    replication=r["replication"],
                    connection_limit=r["connection_limit"],
                    member_of=list(r["member_of"] or []),
                    comment=r["comment"],
                )
            )
        self.report.record_extracted("roles", len(roles))
        return roles
