"""MCP resources - read-only banking data exposed as URIs.

Resources let MCP clients fetch context (schema, domain queries, dialects)
without invoking a tool. They mirror the tool surface but use the
``banking://...`` URI scheme so a client can subscribe / cache them.
"""

from .banking_resources import register_banking_resources


def register_all_resources(mcp) -> None:
    register_banking_resources(mcp)


__all__ = ["register_all_resources"]
