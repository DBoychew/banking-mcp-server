"""
Banking MCP Server — combined FastMCP + FastAPI server.

Mirrors petru's create_combined_app() pattern:
  - FastMCP at /mcp/ (MCP tools endpoint)
  - REST API at /api/* (banking data + config)
  - Streamlit dashboard subprocess (port 8501)
  - Health check at /health

Run modes:
  python main.py        # stdio (Claude Desktop)
  python main.py http   # HTTP server on SERVER_PORT (default 8080)
  python main.py sse    # SSE server (legacy)
"""

import atexit
import datetime
import subprocess
import sys
import urllib.request
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse, Response
from mcp.server.fastmcp import FastMCP

from banking_mcp.config import settings
from banking_mcp.dashboard import DashboardManager
from banking_mcp.tools import register_all_tools
from banking_mcp.resources import register_all_resources
from banking_mcp.prompts import register_all_prompts
from banking_mcp.api import api_router
from banking_mcp.api.middleware import ApiKeyMiddleware
from banking_mcp.audit import start as audit_start, stop as audit_stop, log_error

# ---------------------------------------------------------------------------
# Shared singletons
# ---------------------------------------------------------------------------

_dashboard_manager = DashboardManager()

mcp = FastMCP(
    "banking-assistant",
    instructions=(
        "You are a banking data analytics assistant. "
        "You can query databases, execute Python code to analyze data, "
        "and build dynamic dashboard visualizations. "
        "Use execute_code with the tools object to query data and create charts. "
        "Never invent or guess data — use only results returned by tools."
    ),
    streamable_http_path="/",
)

register_all_tools(mcp, _dashboard_manager)
register_all_resources(mcp)
register_all_prompts(mcp)


@mcp.resource("health://status")
def health_status() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# create_combined_app — mirrors petru's factory pattern
# ---------------------------------------------------------------------------

def create_combined_app() -> FastAPI:
    """
    Build and return the combined FastAPI + MCP application.

    - MCP at /mcp/ (streamable HTTP)
    - REST API at /api/*
    - Streamlit subprocess launched on startup
    """
    streamlit_process: Optional[subprocess.Popen] = None

    def start_streamlit() -> None:
        nonlocal streamlit_process

        if streamlit_process and streamlit_process.poll() is None:
            streamlit_process.terminate()
            streamlit_process.wait()

        import os
        dashboard_path = os.path.join(
            os.path.dirname(__file__), "dashboard", "app.py"
        )

        streamlit_process = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run",
                dashboard_path,
                "--server.port", str(settings.DASHBOARD_PORT),
                "--server.headless", "true",
                "--server.address", "0.0.0.0",
                "--server.runOnSave", "true",
                "--server.fileWatcherType", "poll",
                "--browser.gatherUsageStats", "false",
                "--client.toolbarMode", "minimal",
            ],
        )

    def stop_streamlit() -> None:
        nonlocal streamlit_process
        if streamlit_process and streamlit_process.poll() is None:
            streamlit_process.terminate()
            streamlit_process.wait()

    def is_streamlit_running() -> bool:
        if streamlit_process is not None:
            return streamlit_process.poll() is None

        if not settings.DASHBOARD_AUTOSTART:
            try:
                with urllib.request.urlopen(settings.DASHBOARD_URL, timeout=2):
                    return True
            except Exception:
                return False

        return False

    atexit.register(stop_streamlit)

    if settings.MCP_TRANSPORT == "sse":
        mcp_asgi = mcp.sse_app(mount_path="/mcp")
        session_mgr = None
    else:
        mcp_asgi = mcp.streamable_http_app()
        session_mgr = mcp.session_manager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        audit_start()
        if settings.DASHBOARD_AUTOSTART:
            print("Starting Streamlit dashboard on port", settings.DASHBOARD_PORT)
            start_streamlit()
        else:
            print("Streamlit dashboard managed externally at", settings.DASHBOARD_URL)

        if session_mgr is not None:
            async with session_mgr.run():
                yield
        else:
            yield

        if settings.DASHBOARD_AUTOSTART:
            print("Stopping Streamlit dashboard...")
            stop_streamlit()

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

    application.add_middleware(ApiKeyMiddleware)

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        await log_error(context=request.url.path, error=str(exc))
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    @application.get("/health", tags=["system"])
    async def health():
        return JSONResponse({
            "status": "ok",
            "version": "1.0.0",
            "transport": settings.MCP_TRANSPORT,
            "provider": settings.MCP_PROVIDER,
            "streamlit_running": is_streamlit_running(),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        })

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

    application.include_router(api_router)
    application.mount("/mcp", mcp_asgi)

    return application


# Singleton app instance used by uvicorn
app = create_combined_app()


# ---------------------------------------------------------------------------
# Entry points (called from main.py)
# ---------------------------------------------------------------------------

def run_stdio() -> None:
    mcp.run(transport="stdio")


def run_http() -> None:
    import uvicorn

    print("=" * 70)
    print("Banking MCP Server")
    print("=" * 70)
    print(f"MCP endpoint:  http://localhost:{settings.SERVER_PORT}/mcp/")
    print(f"REST API:      http://localhost:{settings.SERVER_PORT}/api/")
    print(f"Streamlit:     http://localhost:{settings.DASHBOARD_PORT}")
    print("=" * 70 + "\n")

    uvicorn.run(
        "banking_mcp.server:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=(settings.ENV == "dev"),
        log_level=settings.LOG_LEVEL.lower(),
    )
