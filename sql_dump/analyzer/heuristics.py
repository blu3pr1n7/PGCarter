"""Name- and type-based heuristics for inferring column semantics.

These are pure functions over the metadata models — they run identically in
offline and online mode and never touch a database. They drive both the
structural findings (offline) and the choice of profiling query (online).
"""

from __future__ import annotations

import re

from sql_dump.models import Column

# --- data-type families -----------------------------------------------------
# format_type() output is matched case-insensitively on a leading token.

_NUMERIC_RE = re.compile(
    r"^(small|big)?int(eger)?|^numeric|^decimal|^real|^double|^float|^money", re.I
)
_INTEGER_RE = re.compile(r"^(small|big)?int(eger)?$|^serial|^bigserial", re.I)
_TEMPORAL_RE = re.compile(r"^date|^time|^timestamp|^interval", re.I)
_TIMESTAMP_RE = re.compile(r"^timestamp|^date", re.I)
_TEXT_RE = re.compile(r"^text|^char|^character|^varchar|^citext|^name$", re.I)
_BOOLEAN_RE = re.compile(r"^bool", re.I)


def is_numeric(data_type: str) -> bool:
    return bool(_NUMERIC_RE.match(data_type.strip()))


def is_integer(data_type: str) -> bool:
    return bool(_INTEGER_RE.match(data_type.strip()))


def is_temporal(data_type: str) -> bool:
    return bool(_TEMPORAL_RE.match(data_type.strip()))


def is_timestamp(data_type: str) -> bool:
    return bool(_TIMESTAMP_RE.match(data_type.strip()))


def is_text(data_type: str) -> bool:
    return bool(_TEXT_RE.match(data_type.strip()))


def is_boolean(data_type: str) -> bool:
    return bool(_BOOLEAN_RE.match(data_type.strip()))


def supports_aggregates(data_type: str) -> bool:
    """Whether min()/max()/avg() are meaningful for the type."""
    return is_numeric(data_type) or is_temporal(data_type)


# --- name patterns ----------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^(id|uuid|guid)$|_id$|_uuid$|_guid$", re.I)
_TIMESTAMP_NAME_RE = re.compile(
    r"^(created|updated|inserted|modified|deleted)(_at|_on|_date|_time)?$"
    r"|_at$|_on$|^timestamp$|^date$|_date$|_timestamp$",
    re.I,
)
_FRESHNESS_NAME_RE = re.compile(
    r"^(created|updated|inserted|modified)(_at|_on)?$", re.I
)
_EMAIL_RE = re.compile(r"^e?mail(_address)?$|_email$", re.I)
_STATUS_RE = re.compile(r"^(status|state|type|category|kind|mode)$|_status$|_type$", re.I)


def is_identifier_name(name: str) -> bool:
    return bool(_IDENTIFIER_RE.search(name))


def is_timestamp_name(name: str) -> bool:
    return bool(_TIMESTAMP_NAME_RE.search(name))


def is_freshness_name(name: str) -> bool:
    """Names that track row freshness (good for min/max recency checks)."""
    return bool(_FRESHNESS_NAME_RE.search(name))


def is_email_name(name: str) -> bool:
    return bool(_EMAIL_RE.search(name))


def is_status_name(name: str) -> bool:
    return bool(_STATUS_RE.search(name))


def detect_semantics(column: Column) -> list[str]:
    """Return the semantic tags implied by a column's name and type."""
    tags: list[str] = []
    name = column.name
    if is_identifier_name(name):
        tags.append("identifier")
    if is_timestamp_name(name) and (is_temporal(column.data_type) or is_numeric(column.data_type)):
        tags.append("timestamp")
    if is_email_name(name) and is_text(column.data_type):
        tags.append("email")
    if is_status_name(name):
        tags.append("status")
    if is_boolean(column.data_type):
        tags.append("boolean")
    return tags
