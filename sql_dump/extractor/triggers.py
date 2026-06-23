"""Trigger extraction."""

from __future__ import annotations

from sql_dump.extractor.base import Extractor
from sql_dump.models import Trigger

# tgtype bitmask (see catalog/pg_trigger.h)
_ROW = 1 << 0
_BEFORE = 1 << 1
_INSERT = 1 << 2
_DELETE = 1 << 3
_UPDATE = 1 << 4
_TRUNCATE = 1 << 5
_INSTEAD = 1 << 6

_QUERY = """
SELECT
    n.nspname                              AS schema,
    t.tgname                               AS name,
    c.relname                              AS table,
    t.tgtype                               AS tgtype,
    t.tgenabled <> 'D'                     AS enabled,
    pg_catalog.pg_get_triggerdef(t.oid, true) AS definition,
    pn.nspname || '.' || pp.proname        AS function
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc pp ON pp.oid = t.tgfoid
JOIN pg_catalog.pg_namespace pn ON pn.oid = pp.pronamespace
WHERE NOT t.tgisinternal
  AND n.nspname = ANY(%(schemas)s)
ORDER BY n.nspname, c.relname, t.tgname
"""


def _decode(tgtype: int) -> tuple[str, list[str]]:
    if tgtype & _INSTEAD:
        timing = "INSTEAD OF"
    elif tgtype & _BEFORE:
        timing = "BEFORE"
    else:
        timing = "AFTER"
    events = []
    if tgtype & _INSERT:
        events.append("INSERT")
    if tgtype & _UPDATE:
        events.append("UPDATE")
    if tgtype & _DELETE:
        events.append("DELETE")
    if tgtype & _TRUNCATE:
        events.append("TRUNCATE")
    return timing, events


class TriggerExtractor(Extractor):
    name = "trigger"

    def extract(self) -> list[Trigger]:
        triggers: list[Trigger] = []
        for r in self.db.query(_QUERY, {"schemas": self.schemas}):
            timing, events = _decode(r["tgtype"])
            triggers.append(
                Trigger(
                    schema=r["schema"],
                    name=r["name"],
                    table=r["table"],
                    definition=r["definition"],
                    timing=timing,
                    events=events,
                    function=r["function"],
                    enabled=r["enabled"],
                )
            )
        self.report.record_extracted("triggers", len(triggers))
        return triggers
