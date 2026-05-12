"""MCP tools - registers all tools with the FastMCP server."""

from .classification_tools import register_classification_tools
from .db_tools import register_db_tools


def register_all_tools(mcp) -> None:
    register_db_tools(mcp)
    register_classification_tools(mcp)
