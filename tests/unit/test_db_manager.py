"""Tests for banking_mcp.db.manager — SQL validation, schema cache, SQLite path."""

import json
import sqlite3

import pytest

from banking_mcp.db import config as db_config
from banking_mcp.db import manager as mgr_mod


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own SQLite DB and config."""
    db_path = tmp_path / "test.db"
    cfg_path = tmp_path / "db_config.json"
    cache_path = tmp_path / "schema_cache.json"

    # Build a small SQLite DB
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE accounts (id INTEGER, name TEXT, balance REAL)")
    conn.execute("INSERT INTO accounts VALUES (1, 'Alice', 100.5)")
    conn.execute("INSERT INTO accounts VALUES (2, 'Bob', 250.0)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_config, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(mgr_mod, "SCHEMA_CACHE_FILE", cache_path)

    cfg_path.write_text(json.dumps({
        "connections": {
            "test": {
                "name": "test",
                "dsn": f"sqlite:///{db_path}",
                "db_type": "sqlite",
                "description": "test db",
                "schema_filter": {"include": [], "exclude": []},
            }
        },
        "default_connection": "test",
        "domain_queries": {
            "test": {
                "list_accounts": {
                    "sql": "SELECT * FROM accounts ORDER BY id",
                    "description": "all accounts",
                    "params": [],
                },
                "by_id": {
                    "sql": "SELECT * FROM accounts WHERE id = :id",
                    "params": [{"name": "id", "type": "int"}],
                },
            }
        },
    }), encoding="utf-8")

    # Reset singleton
    mgr_mod._manager = None
    return mgr_mod.get_manager()


def test_query_returns_dataframe(isolated_db):
    df = isolated_db.query("SELECT * FROM accounts ORDER BY id")
    assert len(df) == 2
    name_col = "NAME" if "NAME" in df.columns else "name"
    assert df.iloc[0][name_col] == "Alice"


def test_query_validates_select_only(isolated_db):
    with pytest.raises(ValueError, match="Forbidden"):
        isolated_db.query("DELETE FROM accounts")
    with pytest.raises(ValueError, match="Forbidden"):
        isolated_db.query("UPDATE accounts SET balance = 0")
    with pytest.raises(ValueError, match="Forbidden"):
        isolated_db.query("DROP TABLE accounts")


def test_query_allows_keywords_inside_string_literals(isolated_db):
    df = isolated_db.query("SELECT 'DROP TABLE accounts' AS note")
    note_col = "NOTE" if "NOTE" in df.columns else "note"
    assert df.iloc[0][note_col] == "DROP TABLE accounts"


def test_query_rejects_multiple_statements(isolated_db):
    with pytest.raises(ValueError, match="Multiple SQL statements"):
        isolated_db.query("SELECT 1; DELETE FROM accounts")


def test_query_rejects_non_select_calls(isolated_db):
    with pytest.raises(ValueError, match="Forbidden"):
        isolated_db.query("CALL dangerous_proc()")
    with pytest.raises(ValueError, match="Forbidden"):
        isolated_db.query("REPLACE INTO accounts(id) VALUES (1)")


def test_test_connection_works(isolated_db):
    assert isolated_db.test_connection("test") is True


def test_test_connection_returns_false_for_unknown(isolated_db):
    assert isolated_db.test_connection("nonexistent") is False


def test_get_schema_returns_compact_format(isolated_db):
    schema = isolated_db.get_schema("test")
    assert "accounts:" in schema
    assert "id" in schema and "name" in schema and "balance" in schema


def test_schema_cache_persists(isolated_db, tmp_path):
    isolated_db.get_schema("test")
    # Singleton schema_cache survives via _save_schema_cache
    assert "test" in isolated_db.schema_cache


def test_execute_domain_query_no_params(isolated_db):
    df = isolated_db.execute_domain_query("list_accounts")
    assert len(df) == 2


def test_execute_domain_query_with_params(isolated_db):
    df = isolated_db.execute_domain_query("by_id", id=1)
    assert len(df) == 1
    val = df.iloc[0].get("name") or df.iloc[0].get("NAME")
    assert val == "Alice"


def test_execute_domain_query_unknown_raises(isolated_db):
    with pytest.raises(ValueError, match="not found"):
        isolated_db.execute_domain_query("nonexistent")


def test_get_context_for_llm(isolated_db):
    ctx = isolated_db.get_context_for_llm("test")
    assert ctx["connection_name"] == "test"
    assert ctx["db_type"] == "sqlite"
    assert "accounts:" in ctx["schema_compact"]
    assert any(q["name"] == "list_accounts" for q in ctx["domain_queries"])
    assert "test" in ctx["available_connections"]


def test_get_context_for_llm_normalizes_db_type(monkeypatch):
    monkeypatch.setattr(mgr_mod, "load_config", lambda: {"connections": {}, "default_connection": ""})
    monkeypatch.setattr(mgr_mod.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(mgr_mod, "get_default_connection", lambda: "demo")
    monkeypatch.setattr(
        mgr_mod,
        "get_connection",
        lambda name: {"name": name, "db_type": "PostgreSQL", "dsn": "stub"},
    )
    monkeypatch.setattr(
        mgr_mod.DatabaseManager,
        "get_schema",
        lambda self, connection=None, force_refresh=False: "accounts: id(integer)",
    )
    monkeypatch.setattr(
        mgr_mod.DatabaseManager,
        "get_domain_queries_info",
        lambda self, connection=None: [],
    )
    monkeypatch.setattr(mgr_mod.DatabaseManager, "list_connections", lambda self: ["demo"])

    db = mgr_mod.DatabaseManager()
    ctx = db.get_context_for_llm("demo")

    assert ctx["db_type"] == "postgresql"
    assert "PostgreSQL" in ctx["sql_dialect_hint"]


def test_list_connections(isolated_db):
    assert "test" in isolated_db.list_connections()


def test_singleton_returns_same_instance():
    a = mgr_mod.get_manager()
    b = mgr_mod.get_manager()
    assert a is b
