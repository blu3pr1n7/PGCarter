"""Installed extension extraction."""

from __future__ import annotations

from ..models import Extension
from .base import Extractor

_QUERY = """
SELECT
    e.extname              AS name,
    e.extversion           AS version,
    n.nspname              AS schema
FROM pg_catalog.pg_extension e
JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
ORDER BY e.extname
"""


class ExtensionExtractor(Extractor):
    name = "extension"

    def extract(self) -> list[Extension]:
        extensions = [
            Extension(name=r["name"], version=r["version"], schema=r["schema"])
            for r in self.db.query(_QUERY)
        ]
        self.report.record_extracted("extensions", len(extensions))
        return extensions
