"""MCP tools — registers all tools with the FastMCP server."""

from .public_info import register_public_info_tools


def register_all_tools(mcp, dashboard_manager=None) -> None:
    register_public_info_tools(mcp)

    if dashboard_manager is not None:
        from banking_mcp.mcp_tools import register_analytics_tools
        register_analytics_tools(mcp, dashboard_manager)
