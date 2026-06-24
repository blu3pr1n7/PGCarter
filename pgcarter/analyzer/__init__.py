"""Database shape analysis and profiling subsystem.

The analyzer consumes the same metadata models the extractor produces. Its
first input source is the JSON inventory written by :mod:`pgcarter.writers`,
so it can run **offline** (structure-only) without any database access. When a
live connection is supplied it runs **online**, enriching the structural
findings with profiling statistics (row counts, null rates, cardinality,
distributions, freshness).

All analysis queries are read-only ``SELECT`` statements built from quoted,
schema-qualified identifiers; see :mod:`pgcarter.analyzer.queries`.
"""

from __future__ import annotations

from pgcarter.analyzer.config import AnalysisConfig, Thresholds, load_analysis_config
from pgcarter.analyzer.engine import AnalysisEngine
from pgcarter.analyzer.loader import load_inventory
from pgcarter.analyzer.models import (
    AnalysisReport,
    CheckResult,
    ColumnAnalysis,
    TableAnalysis,
    Warning,
)

__all__ = [
    "AnalysisConfig",
    "AnalysisEngine",
    "AnalysisReport",
    "CheckResult",
    "ColumnAnalysis",
    "TableAnalysis",
    "Thresholds",
    "Warning",
    "load_analysis_config",
    "load_inventory",
]
