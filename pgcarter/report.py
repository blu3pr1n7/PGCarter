"""Run report collection: extracted/skipped objects, warnings, and errors."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class SkippedObject:
    object_type: str
    object_name: str
    reason: str


@dataclass
class Report:
    """Accumulates the outcome of an extraction + generation run."""

    database: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    extracted: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: list[SkippedObject] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)

    def record_extracted(self, object_type: str, count: int = 1) -> None:
        self.extracted[object_type] += count

    def record_skipped(self, object_type: str, object_name: str, reason: str) -> None:
        self.skipped.append(SkippedObject(object_type, object_name, reason))

    def record_warning(self, message: str) -> None:
        self.warnings.append(message)

    def record_error(self, message: str) -> None:
        self.errors.append(message)

    def record_file(self, path: Path | str) -> None:
        self.generated_files.append(str(path))

    def finish(self) -> None:
        self.finished_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {
                "extracted": dict(self.extracted),
                "skipped_count": len(self.skipped),
                "warning_count": len(self.warnings),
                "error_count": len(self.errors),
                "generated_file_count": len(self.generated_files),
            },
            "extracted": dict(self.extracted),
            "skipped": [vars(s) for s in self.skipped],
            "warnings": self.warnings,
            "errors": self.errors,
            "generated_files": sorted(self.generated_files),
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False))
