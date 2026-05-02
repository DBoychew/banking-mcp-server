"""API Key authentication and request logging middleware."""

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from banking_mcp.config import settings

# Paths that are exempt from API key validation
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json"}
_PUBLIC_PREFIXES = ("/mcp",)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header for /api/* endpoints and log all REST requests."""

    async def dispatch(self, request: Request, call_next):
        from banking_mcp.audit import log_request

        path = request.url.path
        start = time.perf_counter()

        # Enforce API key on /api/* routes
        if path.startswith("/api/") and path not in _PUBLIC_PATHS:
            api_key = request.headers.get("X-API-Key", "")
            if not api_key or api_key != settings.MCP_API_KEY:
                elapsed = (time.perf_counter() - start) * 1000
                await log_request(
                    method=request.method,
                    path=path,
                    status_code=403,
                    duration_ms=elapsed,
                    client_ip=request.client.host if request.client else None,
                )
                return JSONResponse(
                    {"error": "Invalid or missing API key", "code": "unauthorized"},
                    status_code=403,
                )

        response = await call_next(request)

        # Log all non-MCP HTTP requests
        if not any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            elapsed = (time.perf_counter() - start) * 1000
            await log_request(
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=elapsed,
                client_ip=request.client.host if request.client else None,
            )

        return response
