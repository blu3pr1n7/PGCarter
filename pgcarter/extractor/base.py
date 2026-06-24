"""Base class shared by all asset extractors."""

from __future__ import annotations

from pgcarter.extractor.connection import Database
from pgcarter.logging_config import get_logger
from pgcarter.report import Report


class Extractor:
    """Common machinery for extractors.

    Each concrete extractor pulls one category of asset from the catalogs and
    records progress/warnings/errors against the shared :class:`Report`. A
    failure in one extractor must never abort the whole run, so callers should
    invoke :meth:`safe_extract`.
    """

    #: Human-readable name used in reports and log messages.
    name: str = "object"

    def __init__(self, db: Database, schemas: list[str], report: Report) -> None:
        self.db = db
        self.schemas = schemas
        self.report = report
        self.log = get_logger(f"pgcarter.extractor.{self.name}")
