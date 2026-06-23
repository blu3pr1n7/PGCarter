"""Graphviz DOT writer for the relationship graph."""

from __future__ import annotations

from pathlib import Path

from sql_dump.models import Relationship
from sql_dump.report import Report

_STYLE = {
    "foreign_key": 'color="#1f77b4"',
    "view_dependency": 'color="#2ca02c", style=dashed',
    "trigger": 'color="#ff7f0e"',
    "trigger_dependency": 'color="#ff7f0e", style=dotted',
    "sequence": 'color="#9467bd", style=dotted',
}


def relationships_dot(relationships: list[Relationship]) -> str:
    lines = ["digraph relationships {", "    rankdir=LR;",
             "    node [shape=box, fontname=\"Helvetica\"];", ""]
    nodes: set[str] = set()
    for rel in relationships:
        nodes.add(rel.source)
        nodes.add(rel.target)
    for node in sorted(nodes):
        lines.append(f'    "{node}";')
    lines.append("")
    for rel in relationships:
        style = _STYLE.get(rel.type, "")
        attrs = [f'label="{rel.label or rel.type}"']
        if style:
            attrs.append(style)
        lines.append(f'    "{rel.source}" -> "{rel.target}" [{", ".join(attrs)}];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_dot(path: Path, relationships: list[Relationship], report: Report) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(relationships_dot(relationships))
    report.record_file(path)
