"""MCP tools - registers all tools with the FastMCP server."""

from .db_tools import register_db_tools


def register_all_tools(mcp) -> None:
    register_db_tools(mcp)
