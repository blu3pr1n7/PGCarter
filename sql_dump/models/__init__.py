"""Metadata models for extracted PostgreSQL assets.

These dataclasses are the single source of truth that both the SQL generation
layer and the documentation (Jinja2) rendering layer consume. They are plain
dataclasses (no behaviour beyond serialisation) so they are trivially
serialisable to JSON and passed verbatim into templates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass (or container thereof) to plain data."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


class _Serialisable:
    """Mixin providing a stable ``to_dict`` for JSON output and templates."""

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)  # type: ignore[return-value]


@dataclass
class DatabaseInfo(_Serialisable):
    name: str
    version: str
    encoding: str
    collation: str
    ctype: str
    owner: str
    comment: str | None = None


@dataclass
class Grant(_Serialisable):
    """A single privilege grant on an object."""

    object_type: str  # database | schema | table | column | sequence | function
    object_name: str
    grantee: str
    privilege: str
    grantable: bool = False
    column: str | None = None


@dataclass
class Schema(_Serialisable):
    name: str
    owner: str
    comment: str | None = None
    grants: list[Grant] = field(default_factory=list)


@dataclass
class Column(_Serialisable):
    name: str
    position: int
    data_type: str
    nullable: bool
    default: str | None = None
    is_identity: bool = False
    identity_generation: str | None = None  # ALWAYS | BY DEFAULT
    is_generated: bool = False
    generation_expression: str | None = None
    comment: str | None = None


@dataclass
class Constraint(_Serialisable):
    name: str
    schema: str
    table: str
    type: str  # PRIMARY KEY | FOREIGN KEY | UNIQUE | CHECK | EXCLUDE
    definition: str
    columns: list[str] = field(default_factory=list)
    referenced_schema: str | None = None
    referenced_table: str | None = None
    referenced_columns: list[str] = field(default_factory=list)


@dataclass
class Table(_Serialisable):
    schema: str
    name: str
    owner: str
    kind: str = "table"  # table | partitioned table
    comment: str | None = None
    columns: list[Column] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class Index(_Serialisable):
    schema: str
    name: str
    table: str
    definition: str
    is_unique: bool = False
    is_primary: bool = False
    is_constraint: bool = False  # backs a PK/UNIQUE/EXCLUDE constraint
    method: str = "btree"
    columns: list[str] = field(default_factory=list)
    expressions: list[str] = field(default_factory=list)
    predicate: str | None = None


@dataclass
class View(_Serialisable):
    schema: str
    name: str
    owner: str
    definition: str
    materialized: bool = False
    comment: str | None = None
    columns: list[str] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)


@dataclass
class Parameter(_Serialisable):
    name: str | None
    mode: str  # IN | OUT | INOUT | VARIADIC
    data_type: str
    default: str | None = None


@dataclass
class Function(_Serialisable):
    schema: str
    name: str
    kind: str  # function | procedure | aggregate | window
    signature: str
    arguments: str
    return_type: str | None
    language: str
    volatility: str  # IMMUTABLE | STABLE | VOLATILE
    security_definer: bool
    owner: str
    definition: str
    parameters: list[Parameter] = field(default_factory=list)
    comment: str | None = None
    grants: list[Grant] = field(default_factory=list)


@dataclass
class Trigger(_Serialisable):
    schema: str
    name: str
    table: str
    definition: str
    timing: str  # BEFORE | AFTER | INSTEAD OF
    events: list[str] = field(default_factory=list)  # INSERT/UPDATE/DELETE/TRUNCATE
    function: str | None = None
    enabled: bool = True


@dataclass
class Sequence(_Serialisable):
    schema: str
    name: str
    owner: str
    data_type: str
    start: int
    increment: int
    min_value: int
    max_value: int
    cache: int
    cycle: bool
    owned_by: str | None = None  # table.column it is attached to
    is_identity: bool = False  # internal sequence backing an IDENTITY column
    grants: list[Grant] = field(default_factory=list)


@dataclass
class Extension(_Serialisable):
    name: str
    version: str
    schema: str


@dataclass
class Role(_Serialisable):
    name: str
    superuser: bool = False
    createdb: bool = False
    createrole: bool = False
    inherit: bool = True
    login: bool = False
    replication: bool = False
    connection_limit: int = -1
    member_of: list[str] = field(default_factory=list)
    comment: str | None = None


@dataclass
class Relationship(_Serialisable):
    """An edge in the object dependency / relationship graph."""

    source: str
    target: str
    type: str  # foreign_key | view_dependency | function_dependency | trigger | sequence
    label: str | None = None


@dataclass
class Inventory(_Serialisable):
    """Aggregate of everything extracted from a single database."""

    database: DatabaseInfo
    schemas: list[Schema] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    views: list[View] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    sequences: list[Sequence] = field(default_factory=list)
    extensions: list[Extension] = field(default_factory=list)
    roles: list[Role] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


__all__ = [
    "Column",
    "Constraint",
    "DatabaseInfo",
    "Extension",
    "Function",
    "Grant",
    "Index",
    "Inventory",
    "Parameter",
    "Relationship",
    "Role",
    "Schema",
    "Sequence",
    "Table",
    "Trigger",
    "View",
]
