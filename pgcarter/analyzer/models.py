
"""Result models for the analysis subsystem.

Like the extractor models, these are plain serialisable dataclasses: they are
the single source of truth shared by the JSON writer and the Jinja2 templates.
No formatting or Markdown lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pgcarter.models import _Serialisable

# Severity levels, ordered least → most urgent.
INFO = "info"
WARNING = "warning"
CRITICAL = "critical"

_SEVERITY_ORDER = {INFO: 0, WARNING: 1, CRITICAL: 2}


def severity_rank(severity: str) -> int:
    """Sortable rank for a severity string (unknown → 0)."""
    return _SEVERITY_ORDER.get(severity, 0)


@dataclass
class CheckResult(_Serialisable):
    """The outcome of a single check against a single asset.

    A result with ``severity`` of :data:`WARNING` or :data:`CRITICAL` is also
    surfaced in ``warnings.json``. Informational results (the common case for
    structural observations) carry findings without raising an alarm.

    ``query`` records the exact read-only SQL the check generated. In offline
    mode the query is recorded but not executed (``executed`` is ``False``),
    which lets offline runs document *what would be measured* online.
    """

    check: str
    category: str
    severity: str = INFO
    message: str = ""
    table: str | None = None
    column: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    query: str | None = None
    executed: bool = False


@dataclass
class ColumnAnalysis(_Serialisable):
    name: str
    data_type: str
    nullable: bool
    #: Detected semantics from name/type heuristics, e.g. ["identifier"].
    semantics: list[str] = field(default_factory=list)
    #: Merged profiling statistics (null_percentage, distinct_values, min…).
    stats: dict[str, Any] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)


@dataclass
class TableAnalysis(_Serialisable):
    schema: str
    name: str
    #: Merged table-level metrics (sizes, estimated_rows, …).
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    columns: list[ColumnAnalysis] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class Warning(_Serialisable):
    """A surfaced issue, derived from a non-informational :class:`CheckResult`."""

    severity: str
    category: str
    check: str
    message: str
    table: str | None = None
    column: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisReport(_Serialisable):
    """Top-level analysis output for one database."""

    database: str
    mode: str  # offline | online
    schemas: list[str] = field(default_factory=list)
    generated_at: str = ""
    sample_size: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    tables: list[TableAnalysis] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
