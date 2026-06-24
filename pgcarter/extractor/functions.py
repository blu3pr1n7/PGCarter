"""Function and procedure extraction."""

from __future__ import annotations

from pgcarter.extractor.base import Extractor
from pgcarter.models import Function, Parameter

_QUERY = """
SELECT
    n.nspname                                  AS schema,
    p.proname                                  AS name,
    CASE p.prokind
        WHEN 'f' THEN 'function'
        WHEN 'p' THEN 'procedure'
        WHEN 'a' THEN 'aggregate'
        WHEN 'w' THEN 'window'
    END                                        AS kind,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    CASE WHEN p.prokind IN ('f', 'w')
         THEN pg_catalog.pg_get_function_result(p.oid) END AS return_type,
    l.lanname                                  AS language,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END                                        AS volatility,
    p.prosecdef                                AS security_definer,
    pg_catalog.pg_get_userbyid(p.proowner)     AS owner,
    CASE WHEN p.prokind IN ('f', 'p')
         THEN pg_catalog.pg_get_functiondef(p.oid) END AS definition,
    pg_catalog.obj_description(p.oid, 'pg_proc') AS comment,
    p.proname || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')'
                                               AS signature,
    p.oid                                      AS oid
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language l ON l.oid = p.prolang
WHERE n.nspname = ANY(%(schemas)s)
  AND NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_depend d
      WHERE d.objid = p.oid AND d.deptype = 'e'
  )
ORDER BY n.nspname, p.proname, arguments
"""

_ARGS = """
SELECT
    p.oid AS func_oid,
    t.ord AS ord,
    t.argname AS argname,
    coalesce(t.mode, 'i') AS mode,
    pg_catalog.format_type(t.type_oid, NULL) AS data_type
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
CROSS JOIN LATERAL unnest(
    coalesce(p.proallargtypes, p.proargtypes::oid[]),
    coalesce(p.proargmodes, array_fill('i'::"char", ARRAY[cardinality(p.proargtypes::oid[])])),
    coalesce(p.proargnames, array_fill(NULL::text, ARRAY[cardinality(p.proargtypes::oid[])]))
) WITH ORDINALITY AS t(type_oid, mode, argname, ord)
WHERE n.nspname = ANY(%(schemas)s)
ORDER BY p.oid, t.ord
"""

_MODE = {"i": "IN", "o": "OUT", "b": "INOUT", "v": "VARIADIC", "t": "TABLE"}


class FunctionExtractor(Extractor):
    name = "function"

    def extract(self) -> list[Function]:
        params = {"schemas": self.schemas}
        parameters = self._parameters(params)
        functions: list[Function] = []
        for r in self.db.query(_QUERY, params):
            definition = r["definition"]
            if definition is None:
                # Aggregates/window functions have no pg_get_functiondef form.
                self.report.record_skipped(
                    "function",
                    f"{r['schema']}.{r['signature']}",
                    f"no executable definition available for {r['kind']}",
                )
            functions.append(
                Function(
                    schema=r["schema"],
                    name=r["name"],
                    kind=r["kind"],
                    signature=r["signature"],
                    arguments=r["arguments"],
                    return_type=r["return_type"],
                    language=r["language"],
                    volatility=r["volatility"],
                    security_definer=r["security_definer"],
                    owner=r["owner"],
                    definition=definition or "",
                    parameters=parameters.get(r["oid"], []),
                )
            )
        self.report.record_extracted("functions", len(functions))
        return functions

    def _parameters(self, params: dict) -> dict[int, list[Parameter]]:
        from collections import defaultdict

        grouped: dict[int, list[Parameter]] = defaultdict(list)
        try:
            rows = self.db.query(_ARGS, params)
        except Exception as exc:  # pragma: no cover - defensive
            self.report.record_warning(f"Could not extract function parameters: {exc}")
            return grouped
        for r in rows:
            grouped[r["func_oid"]].append(
                Parameter(
                    name=r["argname"],
                    mode=_MODE.get(r["mode"], "IN"),
                    data_type=r["data_type"],
                )
            )
        return grouped
