"""MCP prompts - domain-specific templates for banking data analysis.

Prompts pre-load schema + dialect context so the LLM can immediately produce
working SQL or Python without first asking the user for orientation.
"""

from .banking_prompts import register_banking_prompts


def register_all_prompts(mcp) -> None:
    register_banking_prompts(mcp)


__all__ = ["register_all_prompts"]
