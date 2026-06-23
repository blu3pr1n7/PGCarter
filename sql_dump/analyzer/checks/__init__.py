"""Check plugins.

Importing this package imports every check module, which registers each check
class via the ``@register`` decorator. To add a new category of checks, create
a module here and add it to the imports below; to add a single check, drop a new
``@register``-decorated class into the relevant module.
"""

from __future__ import annotations

from . import columns, indexes, quality, relationships, statistics, tables

__all__ = ["columns", "indexes", "quality", "relationships", "statistics", "tables"]
