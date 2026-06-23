"""Master ``apply.sql`` writer.

The per-object SQL files are executable when applied in dependency order. This
writer produces a single ordered script that recreates an entire schema in one
run: extensions → roles → schemas → sequences → tables (FK-ordered) → sequence
ownership → indexes → views (dependency-ordered) → functions → triggers →
grants. Ordering is deterministic and independent of any template.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Inventory, Table, View
from ..report import Report
from ..sql import generators as gen
from ..sql.base import header


def _toposort(names: list[str], edges: dict[str, set[str]]) -> list[str]:
    """Return ``names`` ordered so dependencies precede dependents.

    ``edges[a]`` is the set of names that ``a`` depends on (must come first).
    Stable and cycle-tolerant: any remaining nodes in a cycle are appended in
    sorted order so output is always deterministic.
    """
    result: list[str] = []
    visited: set[str] = set()
    temp: set[str] = set()

    def visit(node: str) -> None:
        if node in visited or node not in names:
            return
        if node in temp:  # cycle - break it
            return
        temp.add(node)
        for dep in sorted(edges.get(node, set())):
            visit(dep)
        temp.discard(node)
        visited.add(node)
        result.append(node)

    for name in sorted(names):
        visit(name)
    return result


def _ordered_tables(tables: list[Table]) -> list[Table]:
    by_name = {t.qualified_name: t for t in tables}
    edges: dict[str, set[str]] = {t.qualified_name: set() for t in tables}
    for t in tables:
        for con in t.constraints:
            if con.type == "FOREIGN KEY" and con.referenced_table:
                ref = f"{con.referenced_schema}.{con.referenced_table}"
                if ref != t.qualified_name:
                    edges[t.qualified_name].add(ref)
    return [by_name[n] for n in _toposort(list(by_name), edges)]


def _ordered_views(views: list[View], inv: Inventory) -> list[View]:
    by_name = {f"{v.schema}.{v.name}": v for v in views}
    edges: dict[str, set[str]] = {n: set() for n in by_name}
    for rel in inv.relationships:
        if rel.type == "view_dependency" and rel.source in by_name and rel.target in by_name:
            edges[rel.source].add(rel.target)
    return [by_name[n] for n in _toposort(list(by_name), edges)]


def build_apply_sql(inv: Inventory, timestamp: str) -> str:
    sections: list[str] = [header(inv.database.name, "apply", timestamp).rstrip(),
                           "-- Master script: applies the full schema in dependency order.",
                           ""]

    def section(title: str, statements: list[str]) -> None:
        statements = [s for s in statements if s]
        if not statements:
            return
        sections.append(f"-- {'=' * 70}")
        sections.append(f"-- {title}")
        sections.append(f"-- {'=' * 70}")
        sections.extend(statements)
        sections.append("")

    section("Extensions", [gen.extensions_sql(inv.extensions)] if inv.extensions else [])
    section("Roles", [gen.roles_sql(inv.roles)] if inv.roles else [])
    section("Schemas", [gen.schema_sql(s) for s in inv.schemas])

    seqs = [s for s in inv.sequences if not s.is_identity]
    section("Sequences", [gen.sequence_create_sql(s) for s in seqs])
    section("Tables", [gen.table_sql(t) for t in _ordered_tables(inv.tables)])
    section("Sequence ownership",
            [o for s in seqs if (o := gen.sequence_owned_by_sql(s))])
    section("Indexes",
            [gen.index_sql(i) for i in inv.indexes
             if not (i.is_primary or i.is_constraint)])
    section("Views", [gen.view_sql(v) for v in _ordered_views(inv.views, inv)])
    section("Functions", [gen.function_sql(f) for f in inv.functions])
    section("Triggers", [gen.trigger_sql(t) for t in inv.triggers])
    section("Privileges", [gen.permissions_sql(inv.grants)] if inv.grants else [])

    return "\n".join(sections).rstrip() + "\n"


def write_apply(path: Path, inv: Inventory, timestamp: str, report: Report) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_apply_sql(inv, timestamp))
    report.record_file(path)
