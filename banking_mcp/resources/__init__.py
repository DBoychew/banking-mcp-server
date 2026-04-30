"""
MCP resources — registers all resources with the FastMCP server.
"""

from .account_summary import register_account_resources
from .statement_resource import register_statement_resources


def register_all_resources(mcp) -> None:
    register_account_resources(mcp)
    register_statement_resources(mcp)
