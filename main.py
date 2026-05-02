"""
Entry point for the Banking MCP Server.

Usage:
  python main.py            # uses MCP_TRANSPORT env var (default: stdio)
  python main.py stdio      # Claude Desktop
  python main.py http       # HTTP server on SERVER_PORT (default 8080)
  python main.py sse        # SSE server on SERVER_PORT (legacy)
"""

import sys

from banking_mcp.config import settings


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else settings.MCP_TRANSPORT

    if transport not in {"stdio", "http", "sse"}:
        print(
            f"Unknown transport '{transport}'. Use: stdio, http, sse",
            file=sys.stderr,
        )
        sys.exit(1)

    if transport == "stdio":
        from banking_mcp.server import run_stdio
        run_stdio()
    else:
        # Override transport in settings so create_app() picks the right MCP app
        settings.MCP_TRANSPORT = transport
        from banking_mcp.server import run_http
        run_http()


if __name__ == "__main__":
    main()
