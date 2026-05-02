"""
Analytics MCP tools — petru-style tools for the banking MCP server.

Registers:
  - list_databases()         → available data sources
  - get_database_context()   → schema + domain queries for LLM
  - execute_code()           → Python sandbox with BankingToolsAPI
  - dashboard_add_widget()   → add widget to dynamic dashboard
  - dashboard_update_widget()
  - dashboard_remove_widget()
  - dashboard_view()
"""

from .db_tools import register_db_tools
from .dashboard_tools import register_dashboard_tools


def register_analytics_tools(mcp, dashboard_manager) -> None:
    register_db_tools(mcp)
    register_dashboard_tools(mcp, dashboard_manager)
