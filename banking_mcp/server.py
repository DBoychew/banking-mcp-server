"""
MCP server entry point.

Run modes:
  python -m banking_mcp.server          # stdio (Claude Desktop)
  python -m banking_mcp.server sse      # SSE transport (web clients)
  python main.py                        # same as stdio default
"""

import sys

from mcp.server.fastmcp import FastMCP

from banking_mcp.config import settings
from banking_mcp.tools import register_all_tools
from banking_mcp.resources import register_all_resources
from banking_mcp.prompts import register_all_prompts

mcp = FastMCP(
    "banking-assistant",
    instructions=(
        "You are a secure banking assistant. "
        "You have access to real account data: balances, transactions, statements, "
        "FX rates, and spending analytics. "
        "Always confirm the account before acting on any financial data. "
        "Never invent or guess financial figures — use only data returned by tools."
    ),
)

# ---------------------------------------------------------------------------
# Register all tools, resources, and prompts
# ---------------------------------------------------------------------------

register_all_tools(mcp)
register_all_resources(mcp)
register_all_prompts(mcp)


# ---------------------------------------------------------------------------
# Health resource — used to verify the server is running
# ---------------------------------------------------------------------------

@mcp.resource("health://status")
def health_status() -> str:
    """Server liveness check."""
    return "ok"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else settings.MCP_TRANSPORT
    if transport not in {"stdio", "sse"}:
        print(
            f"Unknown transport '{transport}'. Use 'stdio' or 'sse'.",
            file=sys.stderr,
        )
        sys.exit(1)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
