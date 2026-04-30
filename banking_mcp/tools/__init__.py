"""
MCP banking tools — registers all tools with the FastMCP server.
"""

from .accounts import register_account_tools
from .transactions import register_transaction_tools
from .statement import register_statement_tools
from .fx import register_fx_tools
from .public_info import register_public_info_tools
from .analysis import register_analysis_tools


def register_all_tools(mcp) -> None:
    register_account_tools(mcp)
    register_transaction_tools(mcp)
    register_statement_tools(mcp)
    register_fx_tools(mcp)
    register_public_info_tools(mcp)
    register_analysis_tools(mcp)
