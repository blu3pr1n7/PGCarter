"""The plugin-style rule engine: the :class:`Check` base, registry, and context.

Adding a new check requires only defining a subclass of :class:`TableCheck`,
:class:`ColumnCheck`, or :class:`DatabaseCheck` and decorating it with
:func:`register`. The engine discovers it automatically — no wiring elsewhere.

A check is pure with respect to its asset: it inspects the asset and the shared
:class:`AnalysisContext`, and returns :class:`CheckResult` objects. It never
mutates models. All database access goes through :meth:`AnalysisContext.run`,
which validates every statement as read-only before execution.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..extractor.connection import Database
from ..logging_config import get_logger
from ..models import Column, Constraint, Index, Inventory, Table
from .config import AnalysisConfig
from .models import CheckResult
from .queries import assert_safe, relation

log = get_logger("sql_dump.analyzer.rules")

# An asset passed to a column-scope check.
ColumnAsset = tuple[Table, Column]


@dataclass
class AnalysisContext:
    """Shared state available to every check during a run."""

    inventory: Inventory
    config: AnalysisConfig
    db: Database | None = None
    #: Accumulates every distinct query string the run generated (for auditing).
    generated_queries: list[str] = field(default_factory=list)
    #: Memoises results so checks issuing identical SQL share one round trip.
    _cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # -- mode ---------------------------------------------------------------
    @property
    def online(self) -> bool:
        return self.db is not None

    @property
    def sample_size(self) -> int | None:
        return self.config.sample_size

    def relation_expr(self, table: Table) -> str:
        """FROM expression for ``table`` honouring the configured sample size."""
        return relation(table.schema, table.name, self.config.sample_size)

    # -- query execution ----------------------------------------------------
    def run(self, sql: str) -> list[dict[str, Any]] | None:
        """Validate and execute a read-only query.

        Returns the rows online, or ``None`` offline (the query is still
        recorded so the report documents what would have been measured).
        """
        assert_safe(sql)
        if sql not in self.generated_queries:
            self.generated_queries.append(sql)
        if self.db is None:
            return None
        if sql not in self._cache:
            self._cache[sql] = self.db.query(sql)
        return self._cache[sql]

    def run_one(self, sql: str) -> dict[str, Any] | None:
        rows = self.run(sql)
        return rows[0] if rows else None

    # -- inventory helpers --------------------------------------------------
    def indexes_for(self, table: Table) -> list[Index]:
        return [
            i
            for i in self.inventory.indexes
            if i.schema == table.schema and i.table == table.name
        ]

    def primary_key(self, table: Table) -> Constraint | None:
        for c in table.constraints:
            if c.type == "PRIMARY KEY":
                return c
        return None

    def foreign_keys(self, table: Table) -> list[Constraint]:
        return [c for c in table.constraints if c.type == "FOREIGN KEY"]

    def unique_constraints(self, table: Table) -> list[Constraint]:
        return [c for c in table.constraints if c.type == "UNIQUE"]

    def referenced_by_counts(self) -> dict[str, int]:
        """Map ``schema.table`` → number of inbound foreign keys (offline)."""
        counts: dict[str, int] = defaultdict(int)
        for t in self.inventory.tables:
            for fk in self.foreign_keys(t):
                rs = fk.referenced_schema or t.schema
                if fk.referenced_table:
                    counts[f"{rs}.{fk.referenced_table}"] += 1
        return dict(counts)


# Constraint definitions name their columns; metadata's ``columns`` list is
# often empty, so parse them from the canonical definition as a fallback.
_FK_COLS_RE = re.compile(r"FOREIGN KEY\s*\(([^)]*)\)", re.IGNORECASE)
_CONS_COLS_RE = re.compile(r"\(([^)]*)\)")


def constraint_columns(constraint: Constraint) -> list[str]:
    """Best-effort list of columns a constraint covers."""
    if constraint.columns:
        return list(constraint.columns)
    if constraint.type == "FOREIGN KEY":
        m = _FK_COLS_RE.search(constraint.definition)
    else:
        m = _CONS_COLS_RE.search(constraint.definition)
    if not m:
        return []
    return [c.strip().strip('"') for c in m.group(1).split(",") if c.strip()]


# --- the Check hierarchy ----------------------------------------------------


class Check:
    """Base class for all checks.

    Subclasses set :attr:`name`/:attr:`category` and implement :meth:`applies`
    and :meth:`execute`. The ``scope`` attribute tells the engine which assets
    to feed the check.
    """

    name: str = ""
    category: str = ""
    scope: str = "table"  # table | column | database
    #: Documentation hint: True if the check only produces findings online.
    online_only: bool = False

    def applies(self, asset: Any, ctx: AnalysisContext) -> bool:
        return True

    def execute(self, asset: Any, ctx: AnalysisContext) -> list[CheckResult]:
        raise NotImplementedError

    # Convenience constructor so subclasses don't repeat name/category.
    def result(self, **kwargs: Any) -> CheckResult:
        kwargs.setdefault("check", self.name)
        kwargs.setdefault("category", self.category)
        return CheckResult(**kwargs)


class TableCheck(Check):
    scope = "table"

    def applies(self, asset: Table, ctx: AnalysisContext) -> bool:
        return True

    def execute(self, asset: Table, ctx: AnalysisContext) -> list[CheckResult]:
        raise NotImplementedError


class ColumnCheck(Check):
    scope = "column"

    def applies(self, asset: ColumnAsset, ctx: AnalysisContext) -> bool:
        return True

    def execute(self, asset: ColumnAsset, ctx: AnalysisContext) -> list[CheckResult]:
        raise NotImplementedError


class DatabaseCheck(Check):
    scope = "database"

    def applies(self, asset: Inventory, ctx: AnalysisContext) -> bool:
        return True

    def execute(self, asset: Inventory, ctx: AnalysisContext) -> list[CheckResult]:
        raise NotImplementedError


# --- registry ---------------------------------------------------------------

_REGISTRY: list[type[Check]] = []


def register(cls: type[Check]) -> type[Check]:
    """Class decorator that registers a check for discovery by the engine."""
    if not cls.name:
        raise ValueError(f"Check {cls.__name__} must define a non-empty name")
    _REGISTRY.append(cls)
    return cls


def registered_checks() -> list[type[Check]]:
    """All registered check classes (registration order)."""
    return list(_REGISTRY)


def instantiate_checks(config: AnalysisConfig) -> list[Check]:
    """Instantiate the enabled checks for a run, importing plugins first."""
    # Importing the package registers every check via the @register decorator.
    from . import checks  # noqa: F401  (side-effect import)

    return [cls() for cls in _REGISTRY if config.is_enabled(cls.name)]
