"""Tests for banking_mcp.resources - MCP resource registration and behaviour."""

import json
from unittest.mock import MagicMock

import pytest

from banking_mcp.resources.banking_resources import register_banking_resources


class FakeMCP:
    """Minimal MCP stub that captures registered resources by URI."""

    def __init__(self):
        self.resources = {}

    def resource(self, uri, *_, **__):
        def decorator(fn):
            self.resources[uri] = fn
            return fn
        return decorator


@pytest.fixture
def registered(monkeypatch):
    fake_mcp = FakeMCP()
    fake_db = MagicMock()
    fake_db.list_connections.return_value = ["scards", "bank_info"]
    fake_db.get_connection_info.side_effect = lambda n: {
        "scards": {"name": "scards", "db_type": "oracle", "description": "BANKING_SCHEMA", "is_default": True},
        "bank_info": {"name": "bank_info", "db_type": "sqlite", "description": "Bank info", "is_default": False},
    }.get(n)
    fake_db.get_default_connection.return_value = "scards"
    fake_db.get_schema.return_value = "accounts: id(NUMBER), name(VARCHAR2)"
    fake_db.get_domain_queries_info.return_value = [
        {"name": "active_cards", "description": "...", "parameters": [], "returns": "DataFrame", "example": "..."}
    ]
    monkeypatch.setattr("banking_mcp.resources.banking_resources.get_manager", lambda: fake_db)
    register_banking_resources(fake_mcp)
    return fake_mcp, fake_db


def test_four_resources_registered(registered):
    fake_mcp, _ = registered
    assert set(fake_mcp.resources.keys()) == {
        "banking://databases",
        "banking://schema/{connection}",
        "banking://domain-queries/{connection}",
        "banking://dialects",
    }


def test_databases_resource_returns_json(registered):
    fake_mcp, _ = registered
    out = json.loads(fake_mcp.resources["banking://databases"]())
    assert out["default"] == "scards"
    names = {c["name"] for c in out["connections"]}
    assert names == {"scards", "bank_info"}


def test_schema_resource_uses_connection_arg(registered):
    fake_mcp, db = registered
    out = fake_mcp.resources["banking://schema/{connection}"]("scards")
    assert "accounts:" in out
    db.get_schema.assert_called_with("scards")


def test_schema_resource_returns_error_string_on_failure(registered):
    fake_mcp, db = registered
    db.get_schema.side_effect = ValueError("nope")
    out = fake_mcp.resources["banking://schema/{connection}"]("missing")
    assert out.startswith("Error:")
    assert "nope" in out


def test_domain_queries_resource(registered):
    fake_mcp, _ = registered
    out = json.loads(fake_mcp.resources["banking://domain-queries/{connection}"]("scards"))
    assert out["connection"] == "scards"
    assert out["domain_queries"][0]["name"] == "active_cards"


def test_domain_queries_resource_returns_error_json(registered):
    fake_mcp, db = registered
    db.get_domain_queries_info.side_effect = ValueError("connection not found")
    out = json.loads(fake_mcp.resources["banking://domain-queries/{connection}"]("missing"))
    assert "error" in out


def test_dialects_resource_lists_all_supported(registered):
    fake_mcp, _ = registered
    out = json.loads(fake_mcp.resources["banking://dialects"]())
    assert {
        "oracle",
        "sqlite",
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "duckdb",
        "clickhouse",
    }.issubset(out.keys())
