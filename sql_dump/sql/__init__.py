"""SQL (DDL) generation layer — template-free by design."""

from . import generators
from .base import header, qualified, quote_ident, with_header

__all__ = ["generators", "header", "qualified", "quote_ident", "with_header"]
