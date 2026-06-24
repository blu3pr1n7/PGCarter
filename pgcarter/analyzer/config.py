"""Analysis configuration: enabled checks, thresholds, and sampling.

Loaded from a YAML file (``--config analysis.yml``) shaped as::

    analysis:
      enabled_checks:
        - null_analysis
        - cardinality
        - table_size
      thresholds:
        high_null_percentage: 80
        low_cardinality_limit: 10

Every field has a documented default, so a partial (or absent) config is valid.
When ``enabled_checks`` is omitted, *all* registered checks run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Thresholds:
    """Numeric limits that turn a measurement into a warning."""

    #: Null fraction (percent) at or above which a column is flagged.
    high_null_percentage: float = 80.0
    #: Distinct-value count at or below which a column is "low cardinality".
    low_cardinality_limit: int = 10
    #: Estimated row count at or above which a table is "extremely large".
    large_table_rows: int = 10_000_000
    #: Distinct/total ratio at or above which a column looks like an identifier.
    unique_ratio: float = 0.99
    #: Average text length (chars) above which a text column is flagged "wide".
    long_text_length: int = 10_000

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Thresholds:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class AnalysisConfig:
    """Resolved analysis configuration."""

    enabled_checks: list[str] | None = None
    thresholds: Thresholds = field(default_factory=Thresholds)
    #: Row cap for expensive per-column scans; ``None`` means scan the table.
    sample_size: int | None = None

    def is_enabled(self, check_name: str) -> bool:
        """Whether ``check_name`` should run under this configuration."""
        return self.enabled_checks is None or check_name in self.enabled_checks

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_checks": self.enabled_checks,
            "thresholds": asdict(self.thresholds),
            "sample_size": self.sample_size,
        }


def load_analysis_config(
    path: str | Path | None,
    *,
    sample_size: int | None = None,
) -> AnalysisConfig:
    """Load an :class:`AnalysisConfig` from YAML, applying defaults.

    A missing path yields the default configuration. A CLI ``sample_size``
    overrides any value present in the file.
    """
    data: dict[str, Any] = {}
    if path is not None:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Config file '{path}' must be a YAML mapping")
        data = raw.get("analysis", raw) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config file '{path}' 'analysis' section must be a mapping")

    enabled = data.get("enabled_checks")
    if enabled is not None and not isinstance(enabled, list):
        raise ValueError("'enabled_checks' must be a list of check names")

    thresholds = Thresholds.from_dict(data.get("thresholds") or {})
    resolved_sample = sample_size if sample_size is not None else data.get("sample_size")

    return AnalysisConfig(
        enabled_checks=list(enabled) if enabled is not None else None,
        thresholds=thresholds,
        sample_size=resolved_sample,
    )
