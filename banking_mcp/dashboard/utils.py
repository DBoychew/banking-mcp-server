"""Dashboard helper utilities."""

from __future__ import annotations

from typing import Any

import httpx

from banking_mcp.config import settings

_BASE = f"http://127.0.0.1:{settings.SERVER_PORT}"
_HEADERS = {"X-API-Key": settings.MCP_API_KEY, "Accept": "application/json"}
_TIMEOUT = 10.0


def _get(path: str, params: dict | None = None) -> Any:
    """Synchronous HTTP GET to the local REST API."""
    try:
        resp = httpx.get(f"{_BASE}{path}", headers=_HEADERS, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def fetch_server_config() -> dict:
    return _get("/api/config")


def format_currency(value: str | float | None, currency: str = "BGN") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.2f} {currency}"
    except (ValueError, TypeError):
        return str(value)
