"""Tests for banking_mcp.tools.db_tools — MCP tool registration and behaviour."""

import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

from banking_mcp.tools.db_tools import register_db_tools


class FakeMCP:
    """Minimal MCP stub that captures registered tool functions."""

    def __init__(self):
        self.tools = {}

    def tool(self, *_, **__):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


@pytest.fixture
def registered_tools(monkeypatch):
    fake_mcp = FakeMCP()
    fake_db = MagicMock()
    fake_db.list_connections.return_value = ["scards"]
    fake_db.get_connection_info.return_value = {
        "name": "scards", "db_type": "oracle",
        "description": "Masked Oracle schema", "is_default": True,
    }
    fake_db.get_default_connection.return_value = "scards"
    fake_db.get_context_for_llm.return_value = {
        "connection_name": "scards", "db_type": "oracle",
        "schema_compact": "accounts: id(NUMBER)", "domain_queries": [],
        "available_connections": ["scards"], "sql_dialect_hint": "Oracle",
    }
    monkeypatch.setattr("banking_mcp.tools.db_tools.get_manager", lambda: fake_db)
    register_db_tools(fake_mcp)
    return fake_mcp, fake_db


def test_three_tools_registered(registered_tools):
    fake_mcp, _ = registered_tools
    assert set(fake_mcp.tools.keys()) == {
        "list_databases", "get_database_context", "execute_code"
    }


def test_list_databases_returns_json(registered_tools):
    fake_mcp, _ = registered_tools
    out = json.loads(fake_mcp.tools["list_databases"]())
    assert out["default"] == "scards"
    assert out["connections"][0]["name"] == "scards"
    assert out["connections"][0]["db_type"] == "oracle"


def test_get_database_context_uses_default_when_empty(registered_tools):
    fake_mcp, db = registered_tools
    out = json.loads(fake_mcp.tools["get_database_context"](""))
    assert out["connection_name"] == "scards"
    db.get_context_for_llm.assert_called_with("scards")


def test_get_database_context_explicit_connection(registered_tools):
    fake_mcp, db = registered_tools
    fake_mcp.tools["get_database_context"]("other")
    db.get_context_for_llm.assert_called_with("other")


def test_get_database_context_handles_no_default(registered_tools):
    fake_mcp, db = registered_tools
    db.get_default_connection.return_value = None
    out = json.loads(fake_mcp.tools["get_database_context"](""))
    assert "error" in out


def test_get_database_context_returns_error_on_exception(registered_tools):
    fake_mcp, db = registered_tools
    db.get_context_for_llm.side_effect = ValueError("connection not found")
    out = json.loads(fake_mcp.tools["get_database_context"]("missing"))
    assert out["error"] == "connection not found"


def test_execute_code_success(registered_tools):
    fake_mcp, db = registered_tools
    db.query.return_value = pd.DataFrame([{"cnt": 42}])
    code = 'df = tools.execute_sql_query("SELECT 1")\nresult = df.to_dict("records")'
    out = fake_mcp.tools["execute_code"](code)
    parsed = json.loads(out)
    assert parsed == [{"cnt": 42}]


def test_execute_code_error_returns_error_message(registered_tools):
    fake_mcp, _ = registered_tools
    out = fake_mcp.tools["execute_code"]("import os\nresult = 1")
    assert out.startswith("Error executing code:")
    assert "os" in out
