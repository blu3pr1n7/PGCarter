"""Runtime configuration for pgcarter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Resolved configuration derived from CLI arguments and defaults."""

    host: str
    port: int
    database: str
    user: str
    password: str | None
    output_dir: Path
    templates_dir: Path
    schemas: list[str] = field(default_factory=lambda: ["public"])
    log_level: str = "INFO"

    @property
    def conninfo(self) -> str:
        """Build a libpq connection string (psycopg-compatible)."""
        parts = [
            f"host={self.host}",
            f"port={self.port}",
            f"dbname={self.database}",
            f"user={self.user}",
        ]
        if self.password:
            parts.append(f"password={self.password}")
        return " ".join(parts)

    @property
    def sql_dir(self) -> Path:
        return self.output_dir / "sql"

    @property
    def json_dir(self) -> Path:
        return self.output_dir / "json"

    @property
    def docs_dir(self) -> Path:
        return self.output_dir / "docs"

    @property
    def report_path(self) -> Path:
        return self.output_dir / "report.json"


def resolve_config(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str | None,
    output_dir: str | None,
    templates_dir: str | None,
    schemas: list[str] | None = None,
    log_level: str = "INFO",
) -> Config:
    """Apply documented defaults and return a :class:`Config`.

    Per spec:
      * ``output_dir`` defaults to the database name.
      * ``templates_dir`` defaults to ``./templates``.
      * password may also be supplied via the ``PGPASSWORD`` environment variable.
    """
    resolved_output = Path(output_dir) if output_dir else Path(database)
    resolved_templates = Path(templates_dir) if templates_dir else Path("./templates")
    resolved_password = password if password is not None else os.environ.get("PGPASSWORD")

    return Config(
        host=host,
        port=port,
        database=database,
        user=user,
        password=resolved_password,
        output_dir=resolved_output,
        templates_dir=resolved_templates,
        schemas=schemas or ["public"],
        log_level=log_level,
    )
