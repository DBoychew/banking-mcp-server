"""
Banking MCP Server - FastMCP server (MCP-only, no REST API).

Architecture:
  - FastMCP at /mcp{MCP_HTTP_PATH} (streamable HTTP)
  - Health check at /health

Run modes:
  python main.py        # uses MCP_TRANSPORT env var
  python main.py stdio  # Claude Desktop
  python main.py http   # HTTP server on SERVER_PORT (default 8080)
  python main.py sse    # SSE server (legacy)
"""

import atexit
import datetime
import logging
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from mcp.server.fastmcp import FastMCP

from banking_mcp.audit import log_error, start as audit_start, stop as audit_stop
from banking_mcp.config import settings
from banking_mcp.prompts import register_all_prompts
from banking_mcp.resources import register_all_resources
from banking_mcp.tools import register_all_tools

logger = logging.getLogger(__name__)

_streamlit_process: Optional[subprocess.Popen] = None


def _start_streamlit_subprocess() -> Optional[subprocess.Popen]:
    """Spawn the Streamlit dashboard server in the background.

    Returns the :class:`subprocess.Popen` handle, or ``None`` if startup was
    skipped (autostart disabled, Streamlit not installed, ...).
    """
    global _streamlit_process

    if not settings.DASHBOARD_AUTOSTART:
        return None
    if settings.MCP_TRANSPORT not in {"http", "sse"}:
        return None

    from banking_mcp.dashboard import get_dashboard_manager

    manager = get_dashboard_manager()
    dashboard_id = settings.DASHBOARD_DEFAULT_ID
    app_path = manager._get_app_file(dashboard_id)

    if not app_path.exists():
        app_path.parent.mkdir(parents=True, exist_ok=True)
        app_path.write_text(
            "import streamlit as st\n"
            'st.set_page_config(page_title="Banking Dashboard", layout="wide")\n'
            'st.title("Banking Dashboard")\n'
            'st.info("No widgets configured yet. Use MCP tools to add widgets.")\n',
            encoding="utf-8",
        )

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(settings.DASHBOARD_PORT),
        "--server.headless",
        "true",
        "--server.runOnSave",
        "true",
        "--server.fileWatcherType",
        "poll",
        "--browser.gatherUsageStats",
        "false",
        "--client.toolbarMode",
        "minimal",
    ]

    try:
        _streamlit_process = subprocess.Popen(cmd)
    except FileNotFoundError as exc:
        logger.warning("Streamlit not available, skipping dashboard autostart: %s", exc)
        return None

    logger.info(
        "Streamlit dashboard launched on port %s (pid=%s)",
        settings.DASHBOARD_PORT,
        _streamlit_process.pid,
    )
    return _streamlit_process


def _stop_streamlit_subprocess() -> None:
    global _streamlit_process
    if _streamlit_process is None:
        return
    if _streamlit_process.poll() is None:
        _streamlit_process.terminate()
        try:
            _streamlit_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _streamlit_process.kill()
            _streamlit_process.wait()
    _streamlit_process = None


atexit.register(_stop_streamlit_subprocess)


def get_public_mcp_endpoint_path(mcp_http_path: str | None = None) -> str:
    """Return the externally visible MCP endpoint path."""
    path = settings.MCP_HTTP_PATH if mcp_http_path is None else mcp_http_path
    if path == "/":
        return "/mcp/"
    return f"/mcp{path}"


mcp = FastMCP(
    "banking-assistant",
    instructions=(
        "You are a banking data analytics assistant. "
        "You can query databases and execute Python code to analyze banking data. "
        "Use execute_code with the tools object to query data and analyze results. "
        "Never invent or guess data - use only results returned by tools. "
        "Schema discovery workflow: call get_database_table_list first to see available "
        "tables, then get_table_info for the specific table(s) you need. Only call "
        "get_database_context when you need domain queries or dialect hints as well. "
        "Before writing SQL, read banking://table-descriptions/{connection} to understand "
        "table purposes and column semantics - especially when table names overlap or "
        "multiple columns look similar (e.g. AMOUNT_LOCAL_CCY vs CARD_AMOUNT). "
        "When columns look duplicate or ambiguous, compare their meaning, null/zero "
        "rate, and sample values before choosing one. For top/largest transaction "
        "queries, prefer AMOUNT_LOCAL_CCY when available; use CARD_AMOUNT only when "
        "the user asks for the card-currency/original card amount."
    ),
    streamable_http_path=settings.MCP_HTTP_PATH,
    stateless_http=settings.MCP_STATELESS_HTTP,
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
        _start_streamlit_subprocess()

        try:
            if session_mgr is not None:
                async with session_mgr.run():
                    yield
            else:
                yield
        finally:
            _stop_streamlit_subprocess()

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
                "mcp_endpoint_path": get_public_mcp_endpoint_path(),
                "stateless_http": settings.MCP_STATELESS_HTTP,
                "timestamp": (
                    datetime.datetime.now(datetime.UTC)
                    .isoformat()
                    .replace("+00:00", "Z")
                ),
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
        return RedirectResponse(url=get_public_mcp_endpoint_path(), status_code=307)

    if settings.MCP_HTTP_PATH != "/":
        @application.api_route(
            "/mcp/",
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            include_in_schema=False,
        )
        async def mcp_root_redirect():
            return RedirectResponse(url=get_public_mcp_endpoint_path(), status_code=307)

    application.mount("/mcp", mcp_asgi)

    return application


app = create_combined_app()


def run_stdio() -> None:
    mcp.run(transport="stdio")


def run_http() -> None:
    import uvicorn

    mcp_endpoint_path = get_public_mcp_endpoint_path()

    print("=" * 70)
    print("Banking MCP Server")
    print("=" * 70)
    print(f"MCP endpoint: http://localhost:{settings.SERVER_PORT}{mcp_endpoint_path}")
    print(f"Health:       http://localhost:{settings.SERVER_PORT}/health")
    if settings.DASHBOARD_AUTOSTART and settings.MCP_TRANSPORT in {"http", "sse"}:
        print(
            f"Dashboard:    {settings.DASHBOARD_URL} "
            f"(streamlit on port {settings.DASHBOARD_PORT})"
        )
    print("=" * 70 + "\n")

    uvicorn.run(
        "banking_mcp.server:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=(settings.ENV == "dev"),
        log_level=settings.LOG_LEVEL.lower(),
    )
