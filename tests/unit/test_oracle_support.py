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


def _patch_oracle_manager(monkeypatch, conn_info, run_select_impl):
    """Wire DatabaseManager to a fake Oracle connection + scripted _run_select."""
    monkeypatch.setattr(
        manager, "load_config", lambda: {"connections": {}, "default_connection": ""}
    )
    monkeypatch.setattr(manager.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(manager, "get_default_connection", lambda: conn_info["name"])
    monkeypatch.setattr(manager, "get_connection", lambda name: conn_info)
    monkeypatch.setattr(manager, "_open_connection", lambda info: FakeOracleConnection())
    monkeypatch.setattr(manager, "_run_select", run_select_impl)
    return manager.DatabaseManager()


def test_get_table_keys_returns_pk_and_fk_with_schema(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    def fake_run_select(conn_info, db_conn, sql, params=None):
        calls.append((sql.strip(), params))
        if "constraint_type = 'P'" in sql:
            return ["constraint_name", "column_name"], [("PK_CARDS", "CARD_ID")]
        return (
            ["constraint_name", "column_name", "owner", "table_name", "column_name", "delete_rule"],
            [("FK_CARDS_ACCOUNT", "ACCOUNT_ID", "SCARDS", "ACCOUNTS", "ID", "CASCADE")],
        )

    db = _patch_oracle_manager(
        monkeypatch,
        {
            "name": "scards",
            "db_type": "oracle",
            "dsn": "h/s",
            "schema": "scards",
        },
        fake_run_select,
    )

    keys = db.get_table_keys("scards", "cards")

    assert keys["primary_key"] == {"name": "PK_CARDS", "columns": ["CARD_ID"]}
    assert keys["foreign_keys"] == [
        {
            "name": "FK_CARDS_ACCOUNT",
            "columns": ["ACCOUNT_ID"],
            "references": {"owner": "SCARDS", "table": "ACCOUNTS", "columns": ["ID"]},
            "delete_rule": "CASCADE",
        }
    ]
    # both queries bound :owner + :t and uppercased the table name
    assert all(params == {"owner": "SCARDS", "t": "CARDS"} for _, params in calls)
    assert "all_constraints" in calls[0][0]


def test_get_table_keys_composite_pk(monkeypatch):
    def fake_run_select(conn_info, db_conn, sql, params=None):
        if "constraint_type = 'P'" in sql:
            return [], [
                ("PK_CARD_AUTH", "CARD_ID"),
                ("PK_CARD_AUTH", "AUTH_DATE"),
            ]
        return [], []

    db = _patch_oracle_manager(
        monkeypatch,
        {"name": "scards", "db_type": "oracle", "dsn": "h/s", "schema": "SCARDS"},
        fake_run_select,
    )

    keys = db.get_table_keys("scards", "card_auth")
    assert keys["primary_key"] == {
        "name": "PK_CARD_AUTH",
        "columns": ["CARD_ID", "AUTH_DATE"],
    }
    assert keys["foreign_keys"] == []


def test_get_table_keys_composite_fk(monkeypatch):
    def fake_run_select(conn_info, db_conn, sql, params=None):
        if "constraint_type = 'P'" in sql:
            return [], []
        return [], [
            ("FK_X", "A", "S", "PARENT", "PA", None),
            ("FK_X", "B", "S", "PARENT", "PB", None),
        ]

    db = _patch_oracle_manager(
        monkeypatch,
        {"name": "scards", "db_type": "oracle", "dsn": "h/s", "schema": "S"},
        fake_run_select,
    )

    keys = db.get_table_keys("scards", "child")
    assert keys["foreign_keys"] == [
        {
            "name": "FK_X",
            "columns": ["A", "B"],
            "references": {"owner": "S", "table": "PARENT", "columns": ["PA", "PB"]},
            "delete_rule": None,
        }
    ]


def test_get_table_keys_uses_user_views_when_no_schema(monkeypatch):
    captured: list[str] = []

    def fake_run_select(conn_info, db_conn, sql, params=None):
        captured.append(sql.strip())
        return [], []

    monkeypatch.setattr(manager.settings, "ORACLE_SCHEMA", "")
    db = _patch_oracle_manager(
        monkeypatch,
        {"name": "scards", "db_type": "oracle", "dsn": "h/s", "schema": ""},
        fake_run_select,
    )

    db.get_table_keys("scards", "cards")
    assert all("user_constraints" in sql for sql in captured)
    assert all("all_constraints" not in sql for sql in captured)


def test_get_table_keys_returns_empty_for_non_oracle(monkeypatch):
    monkeypatch.setattr(
        manager, "load_config", lambda: {"connections": {}, "default_connection": ""}
    )
    monkeypatch.setattr(manager.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(manager, "get_default_connection", lambda: "lite")
    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "sqlite", "dsn": "sqlite:///:memory:"},
    )
    db = manager.DatabaseManager()
    assert db.get_table_keys("lite", "anything") == {}


def test_get_schema_keys_groups_pk_and_fk(monkeypatch):
    def fake_run_select(conn_info, db_conn, sql, params=None):
        if "constraint_type = 'P'" in sql:
            return [], [
                ("ACCOUNTS", "PK_ACC", "ID"),
                ("CARDS", "PK_CARD", "CARD_ID"),
            ]
        return [], [
            ("CARDS", "FK_CARD_ACC", "ACCOUNT_ID", "S", "ACCOUNTS", "ID", "CASCADE"),
        ]

    db = _patch_oracle_manager(
        monkeypatch,
        {"name": "scards", "db_type": "oracle", "dsn": "h/s", "schema": "S"},
        fake_run_select,
    )

    out = db.get_schema_keys("scards")
    assert out["primary_keys"] == {
        "ACCOUNTS": {"name": "PK_ACC", "columns": ["ID"]},
        "CARDS": {"name": "PK_CARD", "columns": ["CARD_ID"]},
    }
    assert out["foreign_keys"] == [
        {
            "name": "FK_CARD_ACC",
            "table": "CARDS",
            "columns": ["ACCOUNT_ID"],
            "references": {"owner": "S", "table": "ACCOUNTS", "columns": ["ID"]},
            "delete_rule": "CASCADE",
        }
    ]


def test_get_schema_keys_honours_schema_filter(monkeypatch):
    def fake_run_select(conn_info, db_conn, sql, params=None):
        if "constraint_type = 'P'" in sql:
            return [], [
                ("ACCOUNTS", "PK_ACC", "ID"),
                ("AUDIT_LOG", "PK_AUDIT", "ID"),
            ]
        return [], [
            ("CARDS", "FK_X", "ACC_ID", "S", "ACCOUNTS", "ID", None),
        ]

    db = _patch_oracle_manager(
        monkeypatch,
        {
            "name": "scards",
            "db_type": "oracle",
            "dsn": "h/s",
            "schema": "S",
            "schema_filter": {"include": [], "exclude": ["AUDIT_*"]},
        },
        fake_run_select,
    )

    out = db.get_schema_keys("scards")
    assert "AUDIT_LOG" not in out["primary_keys"]
    assert "ACCOUNTS" in out["primary_keys"]
    assert [fk["table"] for fk in out["foreign_keys"]] == ["CARDS"]


def test_get_schema_keys_returns_empty_for_non_oracle(monkeypatch):
    monkeypatch.setattr(
        manager, "load_config", lambda: {"connections": {}, "default_connection": ""}
    )
    monkeypatch.setattr(manager.DatabaseManager, "_load_schema_cache", lambda self: {})
    monkeypatch.setattr(manager, "get_default_connection", lambda: "lite")
    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "sqlite", "dsn": "sqlite:///:memory:"},
    )
    db = manager.DatabaseManager()
    assert db.get_schema_keys("lite") == {}


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
