"""Tests for banking_mcp.server — FastAPI app structure and /health."""

from fastapi.testclient import TestClient

from banking_mcp.server import app


def test_app_has_health_endpoint():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "transport" in body
    assert "timestamp" in body


def test_root_redirects_to_docs():
    client = TestClient(app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/docs" in r.headers["location"]


def test_favicon_returns_204():
    client = TestClient(app)
    r = client.get("/favicon.ico")
    assert r.status_code == 204


def test_mcp_path_redirects_to_trailing_slash():
    client = TestClient(app)
    r = client.get("/mcp", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"].endswith("/mcp/")


def test_no_api_routes_registered():
    """REST API was deleted - confirm no /api/* routes remain."""
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any(p.startswith("/api") for p in paths), \
        f"Unexpected /api/* routes: {[p for p in paths if p.startswith('/api')]}"


def test_app_has_no_mcp_api_key_setting():
    """Sanity: REST auth middleware was removed with /api package."""
    from banking_mcp.config import settings
    assert not hasattr(settings, "MCP_API_KEY")
    assert not hasattr(settings, "MCP_PROVIDER")
    assert not hasattr(settings, "MCP_TOOLS_ALLOW_MUTATIONS")
