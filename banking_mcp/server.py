"""
Banking MCP Server - FastMCP server (MCP-only, no REST API).

Architecture:
  - FastMCP at /mcp/ (streamable HTTP)
  - Health check at /health

Run modes:
  python main.py        # uses MCP_TRANSPORT env var
  python main.py stdio  # Claude Desktop
  python main.py http   # HTTP server on SERVER_PORT (default 8080)
  python main.py sse    # SSE server (legacy)
"""

import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from mcp.server.fastmcp import FastMCP

from banking_mcp.audit import log_error, start as audit_start, stop as audit_stop
from banking_mcp.config import settings
from banking_mcp.prompts import register_all_prompts
from banking_mcp.resources import register_all_resources
from banking_mcp.tools import register_all_tools

mcp = FastMCP(
    "banking-assistant",
    instructions=(
        "You are a banking data analytics assistant. "
        "You can query databases and execute Python code to analyze banking data. "
        "Use execute_code with the tools object to query data and analyze results. "
        "Never invent or guess data - use only results returned by tools."
    ),
    streamable_http_path="/",
)

register_all_tools(mcp)
register_all_resources(mcp)
register_all_prompts(mcp)


@mcp.resource("health://status")
def health_status() -> str:
    return "ok"


def create_combined_app() -> FastAPI:
    """Build and return the FastAPI application hosting the MCP endpoint."""
    if settings.MCP_TRANSPORT == "sse":
        mcp_asgi = mcp.sse_app(mount_path="/mcp")
        session_mgr = None
    else:
        mcp_asgi = mcp.streamable_http_app()
        session_mgr = mcp.session_manager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        audit_start()

        if session_mgr is not None:
            async with session_mgr.run():
                yield
        else:
            yield

        from banking_mcp.db.manager import get_manager

        get_manager().shutdown()
        audit_stop()

    application = FastAPI(
        title="Banking MCP Server",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        await log_error(context=request.url.path, error=str(exc))
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    @application.get("/health", tags=["system"])
    async def health():
        return JSONResponse(
            {
                "status": "ok",
                "version": "1.0.0",
                "transport": settings.MCP_TRANSPORT,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
            }
        )

    @application.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs", status_code=307)

    @application.api_route(
        "/favicon.ico",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def favicon():
        return Response(status_code=204)

    @application.api_route(
        "/mcp",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def mcp_redirect():
        return RedirectResponse(url="/mcp/", status_code=307)

    application.mount("/mcp", mcp_asgi)

    return application


app = create_combined_app()


def run_stdio() -> None:
    mcp.run(transport="stdio")


def run_http() -> None:
    import uvicorn

    print("=" * 70)
    print("Banking MCP Server")
    print("=" * 70)
    print(f"MCP endpoint: http://localhost:{settings.SERVER_PORT}/mcp/")
    print(f"Health:       http://localhost:{settings.SERVER_PORT}/health")
    print("=" * 70 + "\n")

    uvicorn.run(
        "banking_mcp.server:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=(settings.ENV == "dev"),
        log_level=settings.LOG_LEVEL.lower(),
    )
