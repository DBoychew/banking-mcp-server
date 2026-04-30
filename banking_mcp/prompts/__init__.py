"""
MCP prompts — registers all prompt templates with the FastMCP server.
"""

from .banking_help import register_banking_prompts


def register_all_prompts(mcp) -> None:
    register_banking_prompts(mcp)
