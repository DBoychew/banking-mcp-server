from __future__ import annotations

import sys
from types import SimpleNamespace

from banking_mcp.db import manager


class FakeOracleCursor:
    def __init__(self, rows=None, description=None):
        self.rows = rows or []
        self.description = description or []
        self.executions: list[tuple[str, dict | None]] = []

    def execute(self, sql: str, params=None):
        self.executions.append((sql.strip(), params))

    def fetchall(self):
        return self.rows

    def close(self):
        return None


class FakeOracleConnection:
    def __init__(self, rows=None, description=None):
        self.cursor_obj = FakeOracleCursor(rows=rows, description=description)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_open_connection_uses_oracle_settings_and_schema(monkeypatch):
    captured: dict[str, str] = {}
    fake_connection = FakeOracleConnection()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return fake_connection

    monkeypatch.setitem(sys.modules, "oracledb", SimpleNamespace(connect=fake_connect))
    monkeypatch.setenv("TEST_ORACLE_DSN", "oracle-host.internal:1521/service_name")
    monkeypatch.setenv("TEST_ORACLE_SCHEMA", "BANKING_SCHEMA")
    monkeypatch.setattr(manager.settings, "ORACLE_USER", "scards_user")
    monkeypatch.setattr(manager.settings, "ORACLE_PASSWORD", "secret-pass")
    monkeypatch.setattr(manager.settings, "ORACLE_SCHEMA", "")

    conn = manager._open_connection(
        {
            "name": "scards",
            "db_type": "oracle",
            "dsn": "${TEST_ORACLE_DSN}",
            "schema": "${TEST_ORACLE_SCHEMA}",
        }
    )

    assert conn is fake_connection
    assert captured == {
        "dsn": "oracle-host.internal:1521/service_name",
        "user": "scards_user",
        "password": "secret-pass",
    }
    assert fake_connection.cursor_obj.executions == [
        ("ALTER SESSION SET CURRENT_SCHEMA = BANKING_SCHEMA", None)
    ]


def test_test_connection_uses_dual_for_oracle(monkeypatch):
    fake_connection = FakeOracleConnection(rows=[(1,)], description=[("VALUE",)])

    monkeypatch.setattr(manager, "load_config", lambda: {"connections": {}, "default_connection": ""})
    monkeypatch.setattr(manager.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "oracle", "dsn": "oracle-host.internal:1521/service_name"},
    )
    monkeypatch.setattr(manager, "_open_connection", lambda conn_info: fake_connection)

    db = manager.DatabaseManager()

    assert db.test_connection("scards") is True
    assert fake_connection.cursor_obj.executions == [("SELECT 1 FROM DUAL", None)]
    assert fake_connection.closed is True


def test_execute_sql_returns_rows_for_oracle(monkeypatch):
    fake_connection = FakeOracleConnection(
        rows=[("ACC-001", 125.5)],
        description=[("ACCOUNT_ID",), ("BALANCE",)],
    )

    monkeypatch.setattr(manager, "load_config", lambda: {"connections": {}, "default_connection": ""})
    monkeypatch.setattr(manager.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "oracle", "dsn": "oracle-host.internal:1521/service_name"},
    )
    monkeypatch.setattr(manager, "_open_connection", lambda conn_info: fake_connection)

    db = manager.DatabaseManager()
    rows = db.execute_sql(
        "SELECT account_id, balance FROM accounts WHERE account_id = :account_id",
        connection="scards",
        account_id="ACC-001",
    )

    assert rows == [{"ACCOUNT_ID": "ACC-001", "BALANCE": 125.5}]
    assert fake_connection.cursor_obj.executions == [
        (
            "SELECT account_id, balance FROM accounts WHERE account_id = :account_id",
            {"account_id": "ACC-001"},
        )
    ]
    assert fake_connection.closed is True


def test_fetch_oracle_schema_uppercases_plain_owner(monkeypatch):
    captured = {}
    fake_connection = FakeOracleConnection(rows=[], description=[])

    monkeypatch.setattr(manager, "load_config", lambda: {"connections": {}, "default_connection": ""})
    monkeypatch.setattr(manager.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(manager, "_open_connection", lambda conn_info: fake_connection)

    def fake_run_select(conn_info, db_conn, sql, params=None):
        captured["params"] = params
        return [], []

    monkeypatch.setattr(manager, "_run_select", fake_run_select)

    db = manager.DatabaseManager()
    db._fetch_oracle_schema(
        {
            "name": "scards",
            "db_type": "oracle",
            "dsn": "oracle-host.internal:1521/service_name",
            "schema": "banking_schema",
            "schema_filter": {"include": [], "exclude": []},
        }
    )

    assert captured["params"] == {"owner": "BANKING_SCHEMA"}
