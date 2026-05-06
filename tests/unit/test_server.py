"""Tests for banking_mcp.server - FastAPI app structure and MCP HTTP wiring."""

from fastapi.testclient import TestClient

from banking_mcp.config import Settings
from banking_mcp.server import app, get_public_mcp_endpoint_path


def test_app_has_health_endpoint():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"
    assert body["transport"] in {"stdio", "http", "sse"}
    assert body["mcp_endpoint_path"] == "/mcp/banking-assistant"
    assert body["stateless_http"] is True
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


def test_mcp_path_redirects_to_endpoint_path():
    client = TestClient(app)
    r = client.get("/mcp", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/mcp/banking-assistant"


def test_mcp_root_redirects_to_named_endpoint_path():
    client = TestClient(app)
    r = client.get("/mcp/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/mcp/banking-assistant"


def test_public_mcp_endpoint_path_for_root():
    assert get_public_mcp_endpoint_path("/") == "/mcp/"


def test_public_mcp_endpoint_path_for_named_path():
    assert get_public_mcp_endpoint_path("/banking-assistant") == "/mcp/banking-assistant"


def test_settings_normalize_mcp_http_path():
    assert (
        Settings(_env_file=None, MCP_HTTP_PATH="banking-assistant").MCP_HTTP_PATH
        == "/banking-assistant"
    )
    assert (
        Settings(_env_file=None, MCP_HTTP_PATH="/banking-assistant/").MCP_HTTP_PATH
        == "/banking-assistant"
    )
    assert Settings(_env_file=None, MCP_HTTP_PATH="").MCP_HTTP_PATH == "/"


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
